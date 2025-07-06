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
    assert count_upper("AEIOU") == 3
    assert count_upper("BCDFG") == 0
    assert count_upper("AABBCCDD") == 1
    assert count_upper("AEOUIAE") == 4
    assert count_upper("aeiou") == 0
    assert count_upper("") == 0
    assert count_upper("AEAEAEAE") == 4
    assert count_upper("AEIbcdfgAEI") == 4
    assert count_upper("aBCdEf") == 0  # New test case to detect the fault

    assert count_upper("AEIOU") == 3
    assert count_upper("BCDFG") == 0
    assert count_upper("AABBCCDD") == 1
    assert count_upper("AEOUIAE") == 4
    assert count_upper("aeiou") == 0
    assert count_upper("") == 0
    assert count_upper("AEAEAEAE") == 4
    assert count_upper("AEIbcdfgAEI") == 4
    assert count_upper("aAIOU") == 2  # New test case

    assert count_upper("AEIOU") == 3
    assert count_upper("BCDFG") == 0
    assert count_upper("AABBCCDD") == 1
    assert count_upper("AEOUIAE") == 4
    assert count_upper("aeiou") == 0
    assert count_upper("") == 0
    assert count_upper("AEAEAEAE") == 4
    assert count_upper("AEIbcdfgAEI") == 4
    assert count_upper("aBCdEf") == 0 # Tests for lower case letters
    assert count_upper("abcdefg") == 0 # Tests for lower case letters with no uppercase vowels
    assert count_upper("dBBE") == 0 # Tests for a mix of uppercase and lowercase letters

