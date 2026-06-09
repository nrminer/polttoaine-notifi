from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from news import _title_is_price_relevant


def test_title_filter_rejects_local_station_facility_news():
    assert not _title_is_price_relevant(
        "Katto sortui huoltoasemalla - Rakennustarkastaja kommentoi"
    )
    assert not _title_is_price_relevant(
        "Omistaja kuoli ja perinteinen huoltoasema autioitui - Ovet aukeavat yli vuoden tauon jälkeen"
    )
    assert not _title_is_price_relevant(
        "Nuclear and Natural Gas Are Teaming Up to Power the AI Data Center Boom"
    )
    assert not _title_is_price_relevant(
        "Documents reveal concerns over US company’s proposed gas fracking in WA’s Kimberley region"
    )
    assert not _title_is_price_relevant(
        "Suomalaisten mitta tuli täyteen: 50 kilometrin ajo auton tankkauksen takia on liikaa"
    )


def test_title_filter_keeps_market_and_price_news():
    assert _title_is_price_relevant("Iran conflict: Why has oil stayed near $100 a barrel?")
    assert _title_is_price_relevant("Polttoainevero nousee ensi vuonna")
    assert _title_is_price_relevant("Dieselin hinta laskee huomenna")
