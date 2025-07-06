def select_words(s, n):
    
    result = []
    for word in s.split():
        n_consonants = 0
        for i in range(0, len(word)):
            if word[i].lower() not in ["a","e","i","o","u"]:
                n_consonants += 1 
        if n_consonants == n:
            result.append(word)
    return result




def test():
        assert select_words("hello world", 3) == ['hello']
    assert select_words("this is a test", 2) == []
    assert select_words("example words with consonants", 4) == ["example", "words"]
    assert select_words("a b c d e", 0) == ['a', 'e']
    assert select_words("only vowels aeiou", 0) == ['aeiou']
    assert select_words("", 1) == []
    # New test case to detect fault
    assert select_words("Mary had a little lamb", 3) == ["Mary", "lamb"]
    assert select_words("simple white space", 2) == []
    assert select_words("Hello world", 4) == ["world"]
    assert select_words("Uncle sam", 3) == ["Uncle"]

