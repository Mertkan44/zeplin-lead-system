from datetime import date, datetime, timezone
import unittest
from unittest.mock import patch

from src.ai import pricing, usage
from src.ai.billing_calendar import billing_period


class TimeBasedPricingTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(provider='deepseek',model='deepseek-v4-flash',effective_from='2026-10-13',
                        input_usd_per_m=0.3,cached_input_usd_per_m=0.006,output_usd_per_m=1.2,
                        off_peak_multiplier=0.5,pricing_policy='deepseek_peak_2026')
        self.patcher=patch.object(pricing,'_table_rows',return_value=[self.row]);self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def at(self,stamp):
        return datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)

    def test_both_peak_windows_and_exclusive_ends(self):
        for hour,expected in ((0,'off_peak'),(1,'peak'),(3,'peak'),(4,'off_peak'),
                              (5,'off_peak'),(6,'peak'),(9,'peak'),(10,'off_peak')):
            with self.subTest(hour=hour):
                self.assertEqual(billing_period(self.at(f'2026-10-13T{hour:02}:00:00')),expected)

    def test_weekends_holidays_and_unknown_future_calendar(self):
        self.assertEqual(billing_period(self.at('2026-10-17T07:00:00')),'off_peak')
        self.assertEqual(billing_period(self.at('2026-10-01T07:00:00')),'off_peak')
        self.assertIsNone(billing_period(self.at('2027-01-04T07:00:00')))
        self.assertEqual(billing_period(self.at('2027-01-04T12:00:00')),'off_peak')
        self.assertIsNone(pricing.rates_for('deepseek',self.row['model'],at=self.at('2027-01-04T07:00:00')))

    def test_cached_tokens_billed_separately_and_off_peak_is_half(self):
        split=dict(prompt_tokens=1_000_000,cached_tokens=500_000,completion_tokens=1_000_000)
        peak=pricing.rates_for('deepseek',self.row['model'],at=self.at('2026-10-13T07:00:00'))
        low=pricing.rates_for('deepseek',self.row['model'],at=self.at('2026-10-13T12:00:00'))
        self.assertEqual(pricing.cost_usd(split,peak),1.353)
        self.assertEqual(pricing.cost_usd(split,low),0.6765)

    def test_queued_estimate_reserves_peak_even_when_requested_off_peak(self):
        rate=pricing.rates_for('deepseek',self.row['model'],at=self.at('2026-10-13T12:00:00'),for_estimate=True)
        self.assertEqual((rate['input'],rate['billing_period']),(0.3,'peak_upper_bound'))

    def test_no_retroactive_price_or_guessed_unknown_model(self):
        self.assertIsNone(pricing.rates_for('deepseek',self.row['model'],at=self.at('2026-10-12T07:00:00')))
        self.assertIsNone(pricing.rates_for('deepseek','unknown-model',at=self.at('2026-10-13T07:00:00')))
        self.assertIsNone(pricing.rates_for('deepseek',self.row['model'],on=date(2026,10,13)))

    def test_call_start_controls_rate_when_response_crosses_a_boundary(self):
        # Recording at a later time still uses the start supplied by the provider hook.
        with patch('src.storage.supabase.is_enabled',return_value=False):
            row=usage.record(task='report',provider='deepseek',requested_model=self.row['model'],
                             model=self.row['model'],outcome='success',
                             usage=dict(prompt_tokens=1000,completion_tokens=100),
                             attempted_at=self.at('2026-10-13T03:59:59'))
        self.assertEqual(row['rates']['billing_period'],'peak')
        self.assertEqual(row['actual_cost_usd'],0.00042)

    def test_timezone_is_normalized_and_naive_times_rejected(self):
        self.assertEqual(billing_period(datetime.fromisoformat('2026-10-13T04:00:00+03:00')),'peak')
        with self.assertRaises(ValueError):
            billing_period(datetime(2026,10,13,7))
