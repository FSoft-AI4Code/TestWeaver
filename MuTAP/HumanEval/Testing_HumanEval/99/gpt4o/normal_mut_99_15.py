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
    # New test cases to detect issues in the previous code
    assert closest_integer("1.5000") == 2
    assert closest_integer("-1.5000") == -2
    assert closest_integer("2.4500") == 2
    assert closest_integer("2.5500") == 3
    assert closest_integer("-2.5500") == -3
