def get_closest_vowel(word):

    if len(word) < 3:
        return ""

    vowels = {"a", "e", "i", "o", "u", "A", "E", 'O', 'U', 'I'}
    for i in range(len(word)-2, 0, -1):
        if word[i] in vowels:
            if (word[i+1] not in vowels) and (word[i-1] not in vowels):
                return word[i]
    return ""


def test():
    assert get_closest_vowel("planet") == e
    assert get_closest_vowel("education") == a
    assert get_closest_vowel("brave") == "a"
    assert get_closest_vowel("sky") == ""
    assert get_closest_vowel("apple") == 
    assert get_closest_vowel("aeiou") == ""
    assert get_closest_vowel("bcd") == ""
    assert get_closest_vowel("programming") == i
    assert get_closest_vowel("xylophone") == "o"
