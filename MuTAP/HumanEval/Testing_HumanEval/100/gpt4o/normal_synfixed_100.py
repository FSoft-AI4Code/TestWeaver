def make_a_pile(n):
    
    return [n + 2*i for i in range(n)]

def test():
    assert make_a_pile(0) == []
    assert make_a_pile(1) == [0]
    assert make_a_pile(2) == [0, 2]
    assert make_a_pile(3) == [0, 2, 4]
    assert make_a_pile(4) == [0, 2, 4, 6]
