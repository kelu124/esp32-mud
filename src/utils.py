import json
import sys

if 'esp' in sys.platform:
    from urandom import getrandbits
elif 'WiPy' in sys.platform:
    from ucrypto import getrandbits
else:
    from random import getrandbits

codes = {'resetall': 0, 'bold': 1, 'underline': 4,
         'blink': 5, 'reverse': 7, 'boldoff': 22,
         'blinkoff': 25, 'underlineoff': 24, 'reverseoff': 27,
         'reset': 0, 'black': 30, 'red': 31, 'green': 32,
         'yellow': 33, 'blue': 34, 'magenta': 35, 'cyan': 36,
         'white': 37 }


def password_hash(name, password):
    if sys.platform in ['esp', 'WiPy']:
        import uhashlib
        return ''.join(['%.2x' % i for i in uhashlib.sha1(password + 'weemud' + name).digest()])
    else:
        import hashlib
        return ''.join(['%.2x' % i for i in hashlib.sha1(bytearray(password + 'weemud' + name, 'utf-8')).digest()])


def get_color_list():
    res = {}
    for c in codes:
        res['%' + c] = c
    return res


def get_color(name):
    if name not in codes:
        return ''
    return '\x1b[{}m'.format(codes.get(name, 0))


def multiple_replace(text, replace_words, color_enabled=True):
    for word, replacement in replace_words.items():
        if color_enabled:
            text = text.replace(word, get_color(replacement))
        else:
            text = text.replace(word, '')
    return text

def save_object_to_file(obj, filename):
    with open(filename.lower(), 'w', encoding='utf-8') as f:
        f.write(json.dumps(obj))


def load_object_from_file(filename):
    try:
        with open(filename.lower(), 'r', encoding='utf-8') as f:
            return json.loads(f.read())
    except Exception as e:
        print('Error opening file: ' + filename)
        print(e)
        return None


def randrange(start, stop=None):
    if start == 1:
        return 0
    if stop is None:
        stop = start
        start = 0
    upper = stop - start
    bits = 0
    pwr2 = 1
    while upper > pwr2:
        pwr2 <<= 1
        bits += 1
    while True:
        r = getrandbits(bits)
        if r < upper:
            break
    return r + start


def get_att(d):
    att = 0
    if 'd' in d:
        dice = d.split('d')
        for d in range(int(dice[0])):
            att += randrange(int(dice[1])) + 1
    else:
        att = int(d)
    return att


def calc_att(mud, pid, attacks, bank, attack=None):
    v_att = []
    att = 0
    if attack:
        colors = ['bold', 'yellow']
        v_att.append(attack)
    else:
        colors = ['bold', 'magenta']
        for attack in attacks:
            if attack['cost'] < bank:
                v_att.append(attack)
    # Select a random attack
    if len(v_att) > 0:
        attack = v_att[randrange(len(v_att))]
        att = get_att(attack['dmg'])
        mud.send_message(pid, "%s for %d" % (attack['desc'], att,), color=colors)

        bank -= attack['cost']
    return att, bank
