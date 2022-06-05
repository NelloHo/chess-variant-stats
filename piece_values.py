import argparse
import fileinput
from functools import partial
from math import log
import re

from tqdm import tqdm
import pandas
from sklearn.linear_model import LogisticRegression



def line_count(filename):
    f = open(filename, 'rb')
    bufgen = iter(partial(f.raw.read, 1024*1024), b'')
    return sum(buf.count(b'\n') for buf in bufgen)


SCORE = {'1-0': 1, '0-1': 0, '1/2-1/2': 0.5}


def piece_values(instream, stable_ply, keep_color, ignore_promotion, normalization, rescale):
    # Before the first line has been read, filename() returns None.
    if instream.filename() is None:
        filename = instream._files[0]
    else:
        filename = instream.filename()
    # When reading from sys.stdin, filename() is "-"
    total = None if (filename == "-") else line_count(filename)

    # collect data
    diffs = []
    results = []
    for epd in tqdm(instream, total=total):
        tokens = epd.strip().split(';')
        fen = tokens[0]
        annotations = dict(token.split(' ', 1) for token in tokens[1:])
        board = fen.split(' ')[0]
        pieces = re.findall(r'[A-Za-z]' if ignore_promotion else r'(?:\+)?[A-Za-z]', board)
        result = annotations.get('result')
        if result in ('1-0', '0-1') and int(annotations.get('hmvc', 0)) >= stable_ply:
            black_pov = fen.split(' ')[1] == 'b' and not keep_color
            pov_result = ('1-0' if result == '0-1' else '0-1') if black_pov else result
            diffs.append({p: (pieces.count(p.upper()) - pieces.count(p.lower())) * (-1 if black_pov else 1) for p in set(p.lower() for p in pieces)})
            results.append(SCORE[pov_result])

    # convert to dataframe
    piece_diffs = pandas.DataFrame(diffs)
    piece_diffs.fillna(0, inplace=True)

    # fit
    model = LogisticRegression(solver='liblinear', C=10.0, random_state=0)
    model.fit(piece_diffs, results)

    # print fitted piece values
    if normalization == 'auto':
        norm = min(abs(v) for v in model.coef_[0] if v > 0.05) / rescale
    elif normalization == 'natural':
        norm = log(10) / 2
    elif normalization == 'elo':
        norm = log(10) / 400
    else:
        norm = 1
    for p, v in sorted(zip(piece_diffs.columns, model.coef_[0]), key=lambda x: x[1], reverse=True):
        print(p, '{:.2f}'.format(v / norm))
    print("white" if keep_color else "move", '{:.2f}'.format(model.intercept_[0] / norm))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('epd_files', nargs='*')
    parser.add_argument('-s', '--stable-ply', type=int, default=1, help='minimum ply since last material change')
    parser.add_argument('-c', '--keep-color', action='store_true', help='report color-specific statistics')
    parser.add_argument('-p', '--ignore-promotion', action='store_true', help='ignore promoted state of pieces')
    parser.add_argument('-n', '--normalization', choices=['off', 'elo', 'natural', 'auto'], default='auto', help='define normalization scale, one of %(choices)s')
    parser.add_argument('-r', '--rescale', type=float, default=1, help='rescale. only for "auto" normalization')
    args = parser.parse_args()
    if args.rescale != 1 and args.normalization != 'auto':
        parser.error('Rescaling only supported for "auto" normalization.')

    with fileinput.input(args.epd_files) as instream:
        piece_values(instream, args.stable_ply, args.keep_color, args.ignore_promotion,
                     args.normalization, args.rescale)
