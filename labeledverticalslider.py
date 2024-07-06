#!/usr/bin/python3

import math
from typing import TypeVar, Generic
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

_T = TypeVar('_T', int, float)
class LabeledVerticalSlider(QWidget, Generic[_T]):
    value_changed = pyqtSignal(float)
    font_label = QFont("sans-serif", 10, 600, False)
    slider:QSlider
    
    def __init__(self, display_text:str, values:list[_T], default:_T|None, data_type:type[_T]):
        super().__init__()
        self.display_text = display_text
        self.values = values
        self.default = default
        self.data_type = data_type
        self._internal_value = default
        self._setup_ui()
        self._reset_value()
    
    def _setup_ui(self):
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setTickInterval(1)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBothSides)
        self.slider.setRange(0, len(self.values)-1)
        #self.slider.setFixedWidth(70)
        self.slider.valueChanged.connect(self._value_changed)
        
        self.label = QLabel(self.display_text)
        self.label.setFont(self.font_label)
        self.label.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_value = QLabel()
        self.lbl_value.setContentsMargins(0, 0, 0, 0)
        
        self.v_layout = QHBoxLayout()
        self.v_layout.setSpacing(0)
        self.v_layout.setAlignment(Qt.AlignVCenter)  # type: ignore
        self.v_layout.setContentsMargins(0, 0, 0, 0)
        
        self.v_layout.addWidget(self.label)
        self.v_layout.addWidget(self.lbl_value)
        self.v_layout.addWidget(self.slider)
        
        self.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.v_layout)
    
    def setNewValues(self, new_values:list[_T]):
        print('setNewValues', self.display_text, new_values)
        self.values = new_values
        self.setValue(self.slider.getValue())

    def getClosestValue(self, next_val:_T) -> _T|None:
        closest = None
        closest_diff = math.inf
        for v in self.values:
            diff = abs(next_val - v)
            if diff == closest_diff:
                return v
            if diff < closest_diff:
                closest = v
                closest_diff = diff
        return closest
    
    def setValue(self, new_value:_T):
        print('setValue', self.display_text, new_value)
        self._internal_value = new_value
        closest = self.getClosestValue(new_value)
        if closest is not None:
            self.slider.setValue(self.values.index(closest))
        self.lbl_value.setText(f'{closest}')      
    
    def value(self) -> _T:
        if self._internal_value is not None:
            return self._internal_value
        return self.values[self.slider.value()]
    
    def _value_changed(self, new_value):
        print('_value_changed', self.display_text, new_value)
        try:
            value = self.values[new_value]
        except IndexError as e:
            print('new_value not found', new_value)
            print('field:', self.field)
            return
        self.value_changed.emit(value)
        self.lbl_value.setText(f'{value}')

    def _reset_value(self):
        if self.default is not None:
            self.slider.setValue(self.values.index(self.default))
