#!/usr/bin/env python
#
# Copyright 2019 Flavio Garcia
# Copyright 2016-2017 Veeti Paananen under MIT License
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
ACME API client.
"""

import copy
from collections import namedtuple
from urllib.parse import urljoin, urlparse

import requests

from . import get_version
from .crypto import generate_header, sign_request, sign_request_v2
from .errors import AccountAlreadyExistsError, AcmeError

DEFAULT_HEADERS = {
    'User-Agent': "automatoes {} (https://candango.org/p/automatoes)".format(
        get_version()),
}


class Acme:

    def __init__(self, url, account, directory="directory", verify=None):
        self.url = url
        self.account = None
        self.directory = directory
        self.verify = verify
        self.set_account(account)

    def set_account(self, account):
        self.account = account

    @property
    def key(self):
        if self.account is None:
            return None
        return self.account.key

    def get_directory(self):
        return self.get("/directory")

    def get_nonce(self):
        """
        Gets a new nonce.
        """
        return self.get('/directory').headers.get('Replay-Nonce')

    def get_headers(self):
        """
        Builds a new pair of headers for signed requests.
        """
        header = generate_header(self.account.key)
        protected_header = copy.deepcopy(header)
        protected_header['nonce'] = self.get_nonce()
        return header, protected_header

    def register(self, email):
        """
        Registers the current account on the server.
        """
        response = self.post("/acme/new-reg", {
            'resource': "new-reg",
            'contact': [
                "mailto:{}".format(email)
            ],
        })
        uri = response.headers.get("Location")
        if response.status_code == 201:
            self.account.uri = uri

            # Find terms of service from link headers
            terms = response.links.get("terms-of-service")

            return RegistrationResult(
                contents=_json(response),
                uri=uri,
                terms=(terms['url'] if terms else None)
            )
        elif response.status_code == 409:
            raise AccountAlreadyExistsError(response, uri)
        raise AcmeError(response)

    def get_registration(self):
        """
        Gets available account information from the server.
        """
        response = self.post(self.account.uri, {
            'resource': "reg",
        })
        if str(response.status_code).startswith("2"):
            return _json(response)
        raise AcmeError(response)

    def update_registration(self, params=None):
        """
        Updates registration information on the server.
        """
        params = params or {}
        params['resource'] = "reg"

        response = self.post(self.account.uri, params)
        if str(response.status_code).startswith("2"):
            return True
        raise AcmeError(response)

    def new_authorization(self, domain):
        """
        Requests a new authorization for the specified domain.
        """
        response = self.post('/acme/new-authz', {
            'resource': "new-authz",
            'identifier': {'type': "dns", 'value': domain}
        })
        if response.status_code == 201:
            return NewAuthorizationResult(_json(response), response.headers.get('Location'))
        raise AcmeError(response)

    def validate_authorization(self, uri, _type, key_authorization):
        """
        Marks the specified validation as complete.
        """
        response = self.post(uri, {
            'resource': "challenge",
            'type': _type,
            'keyAuthorization': key_authorization,
        })
        if str(response.status_code).startswith('2'):
            return True
        raise AcmeError(response)

    def get_authorization(self, uri):
        """
        Returns the authorization status.
        """
        response = self.get(uri)
        try:
            return response.json()
        except (ValueError, TypeError, AttributeError) as e:
            raise AcmeError(e)

    def issue_certificate(self, csr):
        http_headers = {'Accept': "application/pkix-cert"}
        response = self.post('/acme/new-cert', {
            'resource': "new-cert",
            'csr': csr,
        }, headers=http_headers)
        if response.status_code == 201:
            # Get the issuer certificate
            chain = response.links.get("up")
            if chain:
                chain = requests.get(chain['url'],
                                     headers=DEFAULT_HEADERS).content
            return IssuanceResult(
                response.content,
                response.headers.get("Location"),
                chain,
            )
        raise AcmeError(response)

    def revoke_certificate(self, cert):
        response = self.post('/acme/revoke-cert', {
            'resource': "revoke-cert",
            'certificate': cert,
        })
        if response.status_code == 200:
            return True
        raise AcmeError(response)

    def get(self, path, headers=None):
        _headers = DEFAULT_HEADERS.copy()
        if headers:
            _headers.update(headers)
        kwargs = {
            'headers': _headers
        }

        if self.verify:
            kwargs['verify'] = self.verify

        return requests.get(self.path(path), **kwargs)

    def post(self, path, body, headers=None):
        _headers = DEFAULT_HEADERS.copy()
        _headers['Content-Type'] = "application/json"
        if headers:
            _headers.update(headers)

        header, protected = self.get_headers()
        body = sign_request(self.account.key, header, protected, body)

        kwargs = {
            'headers': _headers
        }

        if self.verify:
            kwargs['verify'] = self.verify

        return requests.post(self.path(path), data=body, **kwargs)

    def path(self, path):
        # Make sure path is relative
        if path.startswith("http"):
            path = urlparse(path).path
        return urljoin(self.url, path)


RegistrationResult = namedtuple("RegistrationResult", "contents uri terms")
NewAuthorizationResult = namedtuple("NewAuthorizationResult", "contents uri")
IssuanceResult = namedtuple("IssuanceResult",
                            "certificate location intermediate")


class AcmeV2(Acme):

    def head(self, path, headers=None):
        _headers = DEFAULT_HEADERS.copy()
        if headers:
            _headers.update(headers)

        kwargs = {
            'headers': _headers
        }

        if self.verify:
            kwargs['verify'] = self.verify

        return requests.head(self.path(path), **kwargs)

    def get_headers(self, url=None):
        """
        Builds a new pair of headers for signed requests.
        """
        header = generate_header(self.account.key)
        protected_header = copy.deepcopy(header)
        protected_header['nonce'] = self.get_nonce()
        if url is not None:
            protected_header['url'] = url
        return protected_header

    def get_directory(self):
        return self.get("/{}".format(self.directory))

    def url_from_directory(self, what_url):
        response = self.get_directory()
        if response.status_code == 200:
            return response.json()[what_url]
        return None

    def terms_from_directory(self):
        response = self.get_directory()
        if response.status_code == 200:
            if "meta" in response.json():
                if "termsOfService" in response.json()['meta']:
                    return response.json()['meta']['termsOfService']
        return None

    def get_nonce(self):
        """ Gets a new nonce.
        """
        return self.head(self.url_from_directory('newNonce'), {
            'resource': "new-reg",
            'payload': None,
        }).headers.get('Replay-Nonce')

    def register(self, email):
        """Registers the current account on the server.
        """
        payload = {
           "termsOfServiceAgreed": True,
           "contact": [
             "mailto:{email}".format(email=email)
           ]
         }
        response = self.post(
            self.url_from_directory('newAccount'),
            payload
        )

        uri = response.headers.get("Location")

        if response.status_code == 201:
            self.account.uri = uri

            # Find terms of service from link headers
            terms = self.terms_from_directory()

            return RegistrationResult(
                contents=_json(response),
                uri=uri,
                terms=terms
            )
        elif response.status_code == 409:
            raise AccountAlreadyExistsError(response, uri)
        raise AcmeError(response)

    def post(self, path, body, headers=None):
        _headers = DEFAULT_HEADERS.copy()
        _headers['Content-Type'] = "application/jose+json"
        if headers:
            _headers.update(headers)

        protected = self.get_headers(url=self.path(path))
        body = sign_request_v2(self.account.key, protected, body)

        kwargs = {
            'headers': _headers
        }

        if self.verify:
            kwargs['verify'] = self.verify

        return requests.post(self.path(path), data=body, **kwargs)


def _json(response):
    try:
        return response.json()
    except ValueError as e:
        raise AcmeError("Invalid JSON response. {}".format(e))