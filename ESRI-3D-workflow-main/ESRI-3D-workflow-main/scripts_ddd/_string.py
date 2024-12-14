
#############################################
# List utilities

# XX Will need a variable length version of these:
def shift_list_forwards_and_wrap(list):
    return list[1:] + list[:1]


def shift_list_backwards_and_wrap(list):
    return list[-1:] + list[:-1]


# In case of equality, first value is returned.
def lesser_of(value1, value2):
    if value1 <= value2:
        return value1
    else:
        return value2


# In case of equality, first value is returned.
def greater_of(value1, value2):
    if value1 >= value2:
        return value1
    else:
        return value2


