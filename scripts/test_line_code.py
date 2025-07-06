#!/usr/bin/env python3

from data_utils import line_code

# Test code với nhiều loại dòng khác nhau và multi-line statements
test_code = '''import os
import sys
from pathlib import Path

# This is a comment
"""This is a docstring"""

class MyClass:
    """Class docstring"""
    
    def __init__(self, value):
        self.value = value
        pass
    
    def my_method(self):
        # Another comment
        if self.value > 0:
            result = self.value * 2
            return result
        else:
            return None
    
    def multi_line_method(self):
        return datetime_module.timedelta(hours=hours, minutes=minutes,
                                        seconds=seconds,
                                        microseconds=microseconds)
    
    def empty_method(self):
        pass

def my_function():
    """Function docstring"""
    x = 10
    y = 20
    z = x + y
    return z

def multi_line_function():
    result = some_complex_calculation(
        param1=value1,
        param2=value2,
        param3=value3
    )
    return result

# Main execution
if __name__ == "__main__":
    obj = MyClass(5)
    result = obj.my_method()
    print(result)
'''

print("Original code:")
print(test_code)
print("\n" + "="*50 + "\n")

print("Lines with actual logic:")
logic_lines = line_code(test_code)
for line_num in logic_lines:
    lines = test_code.split('\n')
    if line_num <= len(lines):
        print(f"Line {line_num}: {lines[line_num-1].strip()}")

print(f"\nTotal logic lines: {len(logic_lines)}")
print(f"Logic line numbers: {logic_lines}") 