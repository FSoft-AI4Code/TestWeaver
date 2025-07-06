def closest_integer(value):
    
    from math import floor, ceil

    if value.count('.') == 1:
        # remove trailing zeros
        while (value[-1] == '0'):
            value = value[:-1]

    num = float(value)
    if value[-2:] == '.5':
        if num > 0:
            res = ceil(num)
        else:
            res = floor(num)
    elif len(value) > 0:
        res = int(round(num))
    else:
        res = 0

    return res




def test():

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("1.50") == 2
    assert closest_integer("10.50") == 11

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("") == 0  # This should handle empty string input gracefully

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("105.00") == 105  # New test case to check the fault
    assert closest_integer("10.50") == 11    # New test case to check the fault
    assert closest_integer("-10.50") == -11  # New test case to check the fault

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("10") == 10
    assert closest_integer("15.3") == 15
    assert closest_integer("-14.5") == -15
    assert closest_integer("14.5") == 15

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("15.3") == 15

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("1.5000") == 2
    assert closest_integer("-1.5000") == -2
    assert closest_integer("2.4500") == 2
    assert closest_integer("2.5500") == 3
    assert closest_integer("-2.5500") == -3

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("10.") == 10
    assert closest_integer("100.") == 100

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("1.500") == 2  # New test case to detect the fault
    assert closest_integer("-1.500") == -2  # New test case to detect the fault

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("10") == 10
    assert closest_integer("15.3") == 15
    assert closest_integer("14.50") == 15
    assert closest_integer("-14.50") == -15
    assert closest_integer("1.5000") == 2
    assert closest_integer("-1.5000") == -2

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("-0.5000") == -1  # New test case to detect the fault

    assert closest_integer("10") == 10
    assert closest_integer("15.3") == 15
    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("10.0") == 10
    assert closest_integer("10.00") == 10
    assert closest_integer("100.000") == 100
    assert closest_integer("3.000") == 3

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("14.5") == 15
    assert closest_integer("-14.5") == -15

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("10") == 10  # new test case
    assert closest_integer("15.3") == 15  # new test case

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("10") == 10
    assert closest_integer("15.3") == 15
    assert closest_integer("14.5") == 15
    assert closest_integer("-14.5") == -15

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("") == 0  # Test for empty string

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("10") == 10  # New test case to test integer input
    assert closest_integer("15.3") == 15  # New test case to test float input with a decimal part not equal to .5

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("15.3") == 15

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("") == 0  # New test case to detect the change

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("15") == 15
    assert closest_integer("-14.5") == -15

    assert closest_integer("3.5") == 4
    assert closest_integer("-3.5") == -4
    assert closest_integer("2.49") == 2
    assert closest_integer("2.50") == 3
    assert closest_integer("-2.50") == -3
    assert closest_integer("0") == 0
    assert closest_integer("5.0") == 5
    assert closest_integer("5.0000") == 5
    assert closest_integer("0.5") == 1
    assert closest_integer("-0.5") == -1
    assert closest_integer("7.4999") == 7
    assert closest_integer("7.5") == 8
    assert closest_integer("10.0") == 10
    assert closest_integer("-10.0") == -10

