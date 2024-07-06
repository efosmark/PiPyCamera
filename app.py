#!/usr/bin/python3

from datetime import datetime
from functools import partial
import pprint
from typing import Any, Callable, NamedTuple, Sequence, TypeVar, Generic

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import (
    QApplication, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget
)

from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput, FfmpegOutput
from picamera2.previews.qt import QGlPicamera2
from libcamera import controls, Transform # type: ignore

from labeledverticalslider import LabeledVerticalSlider # type: ignore

BITRATE = 10000000
CAM_PIXEL_HEIGHT = int(4056 / 2)
CAM_PIXEL_WIDTH = int(3040 / 2)

FPS_VALUES = [*range(1,11), 15, 20, 25, 30]

# Read Only
FIELD_AE_LOCKED = 'AeLocked'
FIELD_SENSOR_TS = 'SensorTimestamp'
FIELD_LUX = 'Lux'
FIELD_COLOR_TEMP = 'ColourTemperature'
FIELD_SENSOR_TEMP = 'SensorTemperature'
FIELD_DIGITAL_GAIN = 'DigitalGain'
FIELD_FRAME_DURATION = 'FrameDuration'

FIELD_AWB_ENABLE = 'AwbEnable'
FIELD_AE_ENABLE = 'AeEnable'
FIELD_FOCUS_FOM = 'FocusFoM'
FIELD_BRIGHTNESS = 'Brightness'
FIELD_CONTRAST = 'Contrast'
FIELD_SHARPNESS = 'Sharpness'
FIELD_EXPOSURE = 'ExposureTime'
FIELD_EXPOSURE_VALUE = 'ExposureValue'
FIELD_ANALOGUE_GAIN = 'AnalogueGain'
FIELD_SATURATION = 'Saturation'
FIELD_FPS = 'FrameRate'

FIELD_CUSTOM_STATUS = 'Status'

MODE_CONFIG_SENSOR = 'Sensor'
MODE_CONFIG_IMAGE = 'Image'
MODE_TAKE_PHOTO = 'Photo'
MODE_TOGGLE_RECORDING = 'Record'

CONTROL_FIELDS_SENSOR = [FIELD_FPS, FIELD_EXPOSURE, FIELD_ANALOGUE_GAIN]
CONTROL_FIELDS_IMAGE = [FIELD_BRIGHTNESS, FIELD_CONTRAST, FIELD_SHARPNESS, FIELD_SATURATION]
STATUS_FIELDS = [FIELD_CUSTOM_STATUS, FIELD_EXPOSURE, FIELD_LUX, FIELD_ANALOGUE_GAIN, FIELD_COLOR_TEMP, FIELD_SENSOR_TEMP, FIELD_FRAME_DURATION]

_T = TypeVar('_T', int, float)
class ControlField(NamedTuple, Generic[_T]):
    field:str
    title:str
    data_type:type[_T]
    values:list[_T]
    value_default:_T|None

class PiCam(QApplication):
    WINDOW_TITLE = 'PiCam'
    status_labels:dict[str, QLabel]
    fields:dict[str, ControlField]
    current_mode:str|None

    def _update_field(self, field, value):
        if field not in self.fields:
            print("field not present", field)
            return
        if value == 0:
            self.picam2.set_controls({ field: self.fields[field].value_default })
            return
        value = self.fields[field].data_type(value)
        self.picam2.set_controls({ field: value })

    def __init__(self):
        super().__init__([])
        self.current_mode = None
        
        self.button_actions = {
            MODE_CONFIG_SENSOR: partial(self.set_mode, MODE_CONFIG_SENSOR),
            MODE_CONFIG_IMAGE: partial(self.set_mode, MODE_CONFIG_IMAGE),
            MODE_TAKE_PHOTO: self.on_button_take_picture_clicked,
            MODE_TOGGLE_RECORDING: self.toggle_recording
        }
        
        self.fields = {
            FIELD_FPS: ControlField(FIELD_FPS, "FPS", int, FPS_VALUES, 10),
            FIELD_EXPOSURE: ControlField(FIELD_EXPOSURE, "Exposure", int, list(range(0, 200000+10000, 10000)), 200000),
            FIELD_ANALOGUE_GAIN: ControlField(FIELD_ANALOGUE_GAIN, "Gain", int, list(range(0, 45)), 1),
            FIELD_BRIGHTNESS: ControlField(FIELD_BRIGHTNESS, "Bright", float, [x/10 for x in range(-10,11)], 0.0),
            FIELD_CONTRAST: ControlField(FIELD_CONTRAST, "Contrast", float, [x/10 for x in range(0, 21)], 1.0),
            FIELD_SHARPNESS: ControlField(FIELD_SHARPNESS, "Sharpness", float, [x/10 for x in range(0, 21)], 1.0),
            FIELD_SATURATION: ControlField(FIELD_SATURATION, "Saturation", float, [x/10 for x in range(0, 21)], 1)
        }

        self._setup_picam()
        self._setup_ui()
        self.setStyleSheet(open('./pipycam/style.css', 'r').read())
        self.picam2.start()

    def _setup_picam(self):
        self.encoder = H264Encoder(BITRATE)
        
        tuning = Picamera2.load_tuning_file("imx477.json")
        # algo = Picamera2.find_tuning_algo(tuning, "rpi.agc")
        # if "channels" in algo:
        #    algo["channels"][0]["exposure_modes"]["normal"] = {"shutter": [10000, 666660], "gain": [1.0, 8.0]}
        # else:
        #    algo["exposure_modes"]["normal"] = {"shutter": [10000, 666660], "gain": [1.0, 8.0]}
        
        self.picam2 = Picamera2(tuning=tuning)
        self.picam2.post_callback = self.post_callback
        self.picam2.configure(self.picam2.create_video_configuration(main={'size':(2028, 1080)}))#, transform=Transform(hflip=1, vflip=1))) # type: ignore #

        self.output_stream = FfmpegOutput("-f mpegts -s 2028x1080 udp://239.0.0.1:1234")
        self.output_mp4 = FfmpegOutput(f"/tmp/video.mp4")
        
        # Start streaming to the network.
        self.picam2.set_controls({
           'AeEnable': False,
           'AwbEnable': False,
           #'HdrMode': controls.HdrModeEnum.MultiExposureUnmerged,
           #'FrameRate': 2,
        })
        
        self.encoder.output = [self.output_stream, self.output_mp4]
        self.picam2.start_encoder(self.encoder, name='main')
        #self.output_stream.start()

        
    def _setup_ui_config_screen(self):
        self.layout_config_screen = QHBoxLayout()
        self.layout_config_screen.setSpacing(0)
        
        self.sliders = {}
        for field in CONTROL_FIELDS_SENSOR:
            self.sliders[field] = LabeledVerticalSlider(field, self.fields[field].values, self.fields[field].value_default, self.fields[field].data_type)
            self.sliders[field].value_changed.connect(partial(self._update_field, field))
            self.sliders[field].setFixedWidth(60)
            self.layout_config_screen.addWidget(self.sliders[field])
        
        self.ui_config_screen = QWidget()
        self.ui_config_screen.setLayout(self.layout_config_screen)
        #self.ui_config_screen.setStyleSheet('border:1px solid white;')
        #self.ui_config_screen.setVisible(False)
    
    def _setup_ui_status_bar(self):
        self.w_status_bar = QWidget()
        self.w_status_bar.setObjectName('status_bar')
        self.w_status_bar.setContentsMargins(0,0,0,0)
        
        self.layout_status_bar = QHBoxLayout()
        self.layout_status_bar.setSpacing(1)
        self.layout_status_bar.setContentsMargins(1,1,1,1)
        self.status_labels = {}
        for field in STATUS_FIELDS:
            self.status_labels[field] = QLabel()
            self.layout_status_bar.addWidget(self.status_labels[field])
        self.w_status_bar.setLayout(self.layout_status_bar)
        self.status_labels[FIELD_CUSTOM_STATUS].setText('Ready.')

    def _setup_ui_button_controls(self):
        self.button_controls = {}
        self.layout_buttons = QVBoxLayout()
        for field, callback in self.button_actions.items():
            self.button_controls[field] = QPushButton(field)
            self.button_controls[field].clicked.connect(callback)
            self.button_controls[field].setFixedSize(60, 60)
            self.layout_buttons.addWidget(self.button_controls[field])    
    
    def _setup_ui(self):
        self._setup_ui_config_screen()
        self._setup_ui_status_bar()
        self._setup_ui_button_controls()
        
        self.qpicamera2 = QGlPicamera2(self.picam2, keep_ar=True) # width=CAM_PIXEL_WIDTH, height=CAM_PIXEL_WIDTH, 
        self.qpicamera2.done_signal.connect(self.capture_done)

        self.layout_h = QHBoxLayout()
        self.layout_h.addLayout(self.layout_buttons, 5)
        self.layout_h.addWidget(self.ui_config_screen, 40)
        self.layout_h.addWidget(self.qpicamera2, 95)
        self.layout_h.setContentsMargins(0, 0, 0, 0)

        self.layout_v = QVBoxLayout()
        self.layout_v.addLayout(self.layout_h, 95)
        self.layout_v.addWidget(self.w_status_bar, 5)
        self.layout_v.setContentsMargins(0, 0, 0, 0)

        self.window = QWidget()
        self.window.setWindowTitle(self.WINDOW_TITLE)
        self.window.showFullScreen()
        self.window.setContentsMargins(0, 0, 0, 0)
        self.window.setLayout(self.layout_v)
        self.setStyleSheet('margin:0; padding: 0;')
        #self.setContentsMargins(0, 0, 0, 0)

    def capture_done(self, job):
        self.picam2.wait(job)

    def post_callback(self, request):
        metadata = request.get_metadata()
        #pprint.pprint(metadata)
        
        for field in self.fields.keys():
            if field not in metadata:
                continue
            if self.sliders[field].value() == self.sliders[field].value():
                continue
            if field == FIELD_FRAME_DURATION:
                max_exposure = metadata[field]
                step_size = max_exposure // 10
                self.sliders[field].setValues(list(range(0, max_exposure + step_size, step_size)))
            self.sliders[field].setValue(metadata[field])
        
        if FIELD_ANALOGUE_GAIN in metadata:
            gain = metadata[FIELD_ANALOGUE_GAIN] * metadata.get(FIELD_DIGITAL_GAIN, 1)
            self.status_labels[FIELD_ANALOGUE_GAIN].setText(f'{int(gain)}x')
        
        if FIELD_EXPOSURE in metadata:
            exposure_milli = metadata[FIELD_EXPOSURE] / 1000.0
            text = f'Ex: {exposure_milli} ms'
            if metadata.get(FIELD_AE_LOCKED, False):
                text += ' (l)'
            self.status_labels[FIELD_EXPOSURE].setText(text)
        
        if FIELD_FRAME_DURATION in metadata:
            dur = metadata[FIELD_FRAME_DURATION] / 1000.0
            fps = 1000 / dur
            self.status_labels[FIELD_FRAME_DURATION].setText(f'{int(dur)} ms/frame ({int(fps)} FPS)')
        
        if FIELD_COLOR_TEMP in metadata:
            self.status_labels[FIELD_COLOR_TEMP].setText(f'{metadata[FIELD_COLOR_TEMP]}K')
        
        if FIELD_LUX in metadata:
            self.status_labels[FIELD_LUX].setText(f'{metadata[FIELD_LUX]:.1f} lux')
        
        if FIELD_SENSOR_TEMP in metadata:
            self.status_labels[FIELD_SENSOR_TEMP].setText(f'{metadata[FIELD_SENSOR_TEMP]}° C')

    def set_status(self, status:str):
        self.status_labels[FIELD_CUSTOM_STATUS].setText(status)

    def set_mode(self, mode:str|None):
        self.ui_config_screen.setVisible(False)
        self.ui_config_screen.setVisible(False)
        
        if mode == MODE_CONFIG_SENSOR:
            self.ui_config_screen.setVisible(False)
        elif mode == MODE_CONFIG_SENSOR:
            self.ui_config_screen.setVisible(False)
        elif mode == MODE_TAKE_PHOTO:
            self.set_status('Taking photo...')
        elif mode == MODE_TOGGLE_RECORDING:
            self.set_status('Recording...')
        else:
            self.set_status('Ready.')
        
        self.current_mode = mode

    def on_button_take_picture_clicked(self):
        self.set_mode(MODE_TAKE_PHOTO)
        cfg = self.picam2.create_still_configuration()
        filename = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
        self.picam2.switch_mode_and_capture_file(
            cfg,
            f"/home/evan/Pictures/{filename}.jpg",
            signal_function=self.qpicamera2.signal_done
        )
        self.set_mode(None)

    def toggle_recording(self):
        if not self.output_mp4.recording:
            self.set_mode(MODE_TOGGLE_RECORDING)
            filename = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
            self.output_mp4.output_filename = f"/home/evan/Videos/{filename}.mp4"
            self.output_mp4.start()
        else:
            self.output_mp4.stop()
            self.set_mode(None)
    
    def start(self):
        self.picam2.start()
        self.window.show()
        return super().exec()


if __name__ == '__main__':
    app = PiCam()
    app.start()