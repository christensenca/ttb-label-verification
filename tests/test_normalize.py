"""Unit tests for pipeline.normalize primitives."""

from __future__ import annotations

import pytest

from pipeline.normalize import (
    apply_consistency_rules,
    clean_for_display,
    expand_state_abbrev,
    fuzzy_ratio,
    norm_text,
    normalize_country_origin,
    normalize_warning_text,
    parse_alcohol_content,
    parse_net_contents,
    strip_country_suffix,
)


class TestNormText:
    @pytest.mark.parametrize(
        "raw, want",
        [
            ("DIAGEO", "diageo"),
            ("  Don Julio  ", "don julio"),
            ("William Grant & Sons Inc.", "william grant and sons inc"),
            ("The Maker's Mark Distillery Inc.", "maker's mark distillery inc"),
            ("New York, NY", "new york ny"),
            ("STAR HILL FARM,\nLORETTO, KY", "star hill farm loretto ky"),
            (None, ""),
        ],
    )
    def test_norm_text(self, raw, want):
        assert norm_text(raw) == want


class TestExpandStateAbbrev:
    @pytest.mark.parametrize(
        "raw, want",
        [
            ("austin tx", "austin texas"),
            ("new york ny", "new york new york"),
            ("loretto ky", "loretto kentucky"),
            ("austin texas", "austin texas"),  # already expanded — idempotent
            ("nowhere xx", "nowhere xx"),  # unknown token left alone
        ],
    )
    def test_expand(self, raw, want):
        assert expand_state_abbrev(raw) == want


class TestStripCountrySuffix:
    @pytest.mark.parametrize(
        "raw, want",
        [
            ("versailles kentucky usa", "versailles kentucky"),
            ("versailles kentucky united states of america", "versailles kentucky"),
            ("new york new york", "new york new york"),  # leave alone
            ("london uk", "london"),
            ("", ""),
        ],
    )
    def test_strip(self, raw, want):
        assert strip_country_suffix(raw) == want


class TestNormalizeCountryOrigin:
    @pytest.mark.parametrize(
        "raw, want",
        [
            ("Mexico", "mexico"),
            ("PRODUCT OF MEXICO", "mexico"),
            ("Product of Scotland", "scotland"),
            ("Distilled and bottled in Scotland", "scotland"),
            (None, ""),
        ],
    )
    def test_normalize(self, raw, want):
        assert normalize_country_origin(raw) == want


class TestParseNetContents:
    @pytest.mark.parametrize(
        "raw, want_ml",
        [
            ("750 mL", 750.0),
            ("750ML", 750.0),
            ("0.75 L", 750.0),
            ("0.75L", 750.0),
            ("1 L", 1000.0),
            ("1.75 L", 1750.0),
            ("375 mL", 375.0),
            ("50 cL", 500.0),
            ("garbage", None),
            (None, None),
        ],
    )
    def test_parse(self, raw, want_ml):
        assert parse_net_contents(raw) == want_ml


class TestParseAlcoholContent:
    @pytest.mark.parametrize(
        "raw, want_abv",
        [
            ("40% Alc./Vol.", 40.0),
            ("ALC. 45% BY VOL.", 45.0),
            ("Alcohol 44% by volume", 44.0),
            ("48.28 ALC/VOL", 48.28),
            (40.0, 40.0),
            ("80 proof", None),
            ("garbage", None),
            (None, None),
        ],
    )
    def test_parse(self, raw, want_abv):
        assert parse_alcohol_content(raw) == want_abv


class TestFuzzyRatio:
    def test_identical(self):
        assert fuzzy_ratio("hello world", "hello world") == 100.0

    def test_close(self):
        # token_sort handles reordered tokens
        assert fuzzy_ratio("william grant and sons", "sons william grant and") >= 90.0

    def test_unrelated(self):
        assert fuzzy_ratio("aardvark", "zeppelin") < 40.0


class TestApplyConsistencyRules:
    def test_imported_null_clears_country(self):
        out = apply_consistency_rules({"is_imported": None, "country_of_origin": "Mexico"})
        assert out["country_of_origin"] is None

    def test_domestic_false_keeps_country(self):
        # Maker's Mark / Tito's / Woodford print "USA" legitimately.
        out = apply_consistency_rules({"is_imported": False, "country_of_origin": "USA"})
        assert out["country_of_origin"] == "USA"

    def test_imported_true_keeps_country(self):
        out = apply_consistency_rules({"is_imported": True, "country_of_origin": "Mexico"})
        assert out["country_of_origin"] == "Mexico"

    def test_returns_copy(self):
        src = {"is_imported": None, "country_of_origin": "Mexico"}
        out = apply_consistency_rules(src)
        assert src["country_of_origin"] == "Mexico"
        assert out is not src


class TestNormalizeWarningText:
    def test_collapses_newlines_and_whitespace(self):
        out = normalize_warning_text("GOVERNMENT WARNING:\n\n(1)   foo\n  bar.")
        assert out == "GOVERNMENT WARNING: (1) foo bar."

    def test_crlf_normalized(self):
        out = normalize_warning_text("GOVERNMENT WARNING:\r\n(1) foo.")
        assert out == "GOVERNMENT WARNING: (1) foo."

    def test_nbsp_normalized(self):
        out = normalize_warning_text("GOVERNMENT WARNING: (1) foo.")
        assert out == "GOVERNMENT WARNING: (1) foo."

    def test_smart_quotes_normalized(self):
        out = normalize_warning_text("“GOVERNMENT WARNING:” ‘foo’")
        assert out == "\"GOVERNMENT WARNING:\" 'foo'"

    def test_markdown_bold_stripped(self):
        out = normalize_warning_text("**GOVERNMENT WARNING:** (1) According to ...")
        assert out == "GOVERNMENT WARNING: (1) According to ..."

    def test_markdown_underscore_stripped(self):
        out = normalize_warning_text("__GOVERNMENT WARNING:__ (1) foo.")
        assert out == "GOVERNMENT WARNING: (1) foo."

    def test_hyphenation_repaired(self):
        # word broken across newline with hyphen
        out = normalize_warning_text("during pregn-\nancy because")
        assert out == "during pregnancy because"

    def test_commas_periods_parens_preserved(self):
        src = "GOVERNMENT WARNING: (1) foo, bar. (2) baz, qux."
        # roundtrip — nothing should be stripped from this clean input
        assert normalize_warning_text(src) == src

    def test_missing_comma_NOT_recovered(self):
        # The whole point: real punctuation deviations must still surface.
        with_comma = normalize_warning_text("MACHINERY, AND MAY CAUSE")
        without = normalize_warning_text("MACHINERY AND MAY CAUSE")
        assert with_comma != without


class TestCleanForDisplay:
    @pytest.mark.parametrize(
        "raw, want",
        [
            ("AUSTIN, TX", "Austin, TX"),
            ("WILLIAM GRANT AND SONS INC", "William Grant and Sons Inc"),
            ("DIAGEO", "Diageo"),
            ("Don Julio", "Don Julio"),  # mixed-case left alone
            ("New York, NY", "New York, NY"),
            ("  trailing space.  ", "trailing space"),
            (None, None),
            (40.0, 40.0),
        ],
    )
    def test_clean(self, raw, want):
        assert clean_for_display(raw) == want
