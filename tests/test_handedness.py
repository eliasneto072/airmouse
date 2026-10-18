"""HandednessStabilizer."""

from core.handedness import HandednessStabilizer


def test_single_hand_label_flicker_is_ignored():
    stab = HandednessStabilizer(stable_frames=5)
    assert stab.assign([(True, 0.4, 0.6)]) == [True]
    for _ in range(4):
        assert stab.assign([(False, 0.4, 0.6)]) == [True]
    assert stab.assign([(False, 0.4, 0.6)]) == [False]  # 5th disagreeing frame


def test_new_hand_elsewhere_trusts_label():
    stab = HandednessStabilizer(stable_frames=5)
    stab.assign([(True, 0.3, 0.6)])
    assert stab.assign([(False, 0.8, 0.6)]) == [False]


def test_two_hands_with_same_label_split_by_position():
    stab = HandednessStabilizer()
    # Raw (unmirrored) frame: the user's right hand appears on the image's left.
    assert stab.assign([(True, 0.7, 0.6), (True, 0.3, 0.6)]) == [False, True]
    mirrored = HandednessStabilizer(mirrored=True)
    assert mirrored.assign([(True, 0.7, 0.6), (True, 0.3, 0.6)]) == [True, False]


def test_two_hands_with_distinct_labels_kept():
    assert HandednessStabilizer().assign([(False, 0.3, 0.6), (True, 0.7, 0.6)]) == [False, True]
