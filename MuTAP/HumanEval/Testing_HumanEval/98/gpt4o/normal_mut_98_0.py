def count_upper(s):
    
    count = 0
    for i in range(0,len(s),2):
        if s[i] in "AEIOU":
            count += 1
    return count



def test():
        assert count_upper("AEIOU") == 3
    assert count_upper("BCDFG") == 0
    assert count_upper("AABBCCDD") == 1
    assert count_upper("AEOUIAE") == 4
    assert count_upper("aeiou") == 0
    assert count_upper("") == 0
    assert count_upper("AEAEAEAE") == 4
    assert count_upper("AEIbcdfgAEI") == 4
    assert count_upper("aAIOU") == 2  # New test case
