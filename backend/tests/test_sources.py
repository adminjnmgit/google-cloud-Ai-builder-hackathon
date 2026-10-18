import io

import pytest

from orbit.pipeline.sources import reports_from_csv

JAGRAN = (
    '#,Section,Headline,Summary,Date (IST),Type,URL,Translated Headline,Translated Summary\n'
    '1,Biz News,hindi head,hindi sum,2026-10-16 13:47,News,http://x/1,Crude surges 5%,Brent is up\n'
    '2,Commodity,hindi head 2,hindi sum 2,2026-10-16 9:40,News,http://x/2,,\n'
    '3,Share Market,hindi head 3,hindi sum 3,garbage,News,http://x/3,Sensex falls,Markets down\n'
)
PLAIN = 'Sl No,Type,Date,Headline,Summary\n7,Biz News,2026-10-01 12:20:00,Petrol costlier by Rs 5,Prices up\n'


def test_jagran_export_uses_english_columns_and_skips_untranslated_rows():
    reports, skipped = reports_from_csv(io.StringIO(JAGRAN))
    assert [r['sl'] for r in reports] == [1]  # row 2 has no translation, row 3 has a bad date
    assert skipped == 1  # only the bad date counts as skipped
    r = reports[0]
    assert (r['type'], r['headline'], r['summary']) == ('Biz News', 'Crude surges 5%', 'Brent is up')
    assert r['date'] == '2026-10-16 13:47'


def test_plain_sheet_is_accepted():
    reports, skipped = reports_from_csv(io.StringIO(PLAIN))
    assert skipped == 0
    assert reports[0]['sl'] == 7
    assert reports[0]['type'] == 'Biz News'


def test_missing_columns_are_reported():
    with pytest.raises(ValueError, match='missing'):
        reports_from_csv(io.StringIO('a,b\n1,2\n'))
