"""A site builder's footer must not become the prospect's social identity."""
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from bs4 import BeautifulSoup

from src.audit.finder import find_instagram, find_tiktok
from src.audit.website import _social_links


class VendorLinksTests(unittest.TestCase):
    def test_template_accounts_are_ignored_and_real_accounts_preserved(self):
        soup = BeautifulSoup('''
            <a href="https://www.instagram.com/Wix/">Builder</a>
            <a href="https://www.facebook.com/wix">Builder</a>
            <a href="https://www.tiktok.com/@wix">Builder</a>
            <a href="https://www.instagram.com/restohankebap/?ref=footer">Business</a>
            <a href="https://www.tiktok.com/@restohankebap">Business</a>
        ''', 'html.parser')
        self.assertEqual(_social_links(soup, 'instagram.com'), ['https://www.instagram.com/restohankebap/'])
        self.assertEqual(_social_links(soup, 'facebook.com'), [])
        self.assertEqual(_social_links(soup, 'tiktok.com'), ['https://www.tiktok.com/@restohankebap'])


class FinderVendorLinksTests(unittest.IsolatedAsyncioTestCase):
    async def test_tiktok_vendor_and_spoofed_host_are_not_business_accounts(self):
        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(lambda request: httpx.Response(404))
        for link in ['https://www.tiktok.com/@wix', 'https://evil.example/tiktok.com/@restohankebap']:
            with self.subTest(link=link), patch('src.audit.finder.httpx.AsyncClient',
                    side_effect=lambda **kwargs: real_client(transport=transport, **kwargs)), \
                    patch('src.audit.finder.asyncio.sleep', new_callable=AsyncMock):
                result = await find_tiktok(None, 'Restohan Kebap', {'tiktok_url': link})
            self.assertIsNone(result['tiktok_url'])
            self.assertIsNone(result['tiktok_username'])
            self.assertIsNone(result['has_tiktok'])

    async def test_business_name_alone_does_not_confirm_a_tiktok_profile(self):
        with patch('src.audit.finder.httpx.AsyncClient') as client:
            result = await find_tiktok(None, 'Klinik Bomonti', {})
        self.assertIsNone(result['has_tiktok'])
        self.assertIsNone(result['tiktok_url'])
        client.assert_not_called()

    async def test_real_tiktok_site_link_is_preserved_without_guessing(self):
        with patch('src.audit.finder.httpx.AsyncClient') as client:
            result = await find_tiktok(None, 'Restohan Kebap', {
                'tiktok_url': 'https://www.tiktok.com/@restohankebap'})
        self.assertTrue(result['has_tiktok'])
        self.assertEqual(result['tiktok_username'], 'restohankebap')
        client.assert_not_called()

    async def test_instagram_template_link_before_real_business_is_skipped(self):
        page = AsyncMock()
        page.content.return_value = '''<a href="https://www.instagram.com/wix/">Wix</a>
            <a href="https://www.instagram.com/restohankebap/">Business</a>'''
        result = await find_instagram(page, 'Restohan Kebap', 'https://restohan.example')
        self.assertEqual(result['instagram_username'], 'restohankebap')
        self.assertEqual(result['identity_confidence'], 98)
