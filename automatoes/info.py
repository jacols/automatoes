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
The account info command.
"""

import json
import logging
import sys

from .acme import Acme
from .errors import AutomatoesError

logger = logging.getLogger(__name__)


def info(server, account):
    acme = Acme(server, account)

    try:
        logger.info("Requesting account data...")
        reg = acme.get_registration()
        sys.stdout.write(json.dumps(reg, indent=4, sort_keys=True))
        sys.stdout.flush()
    except IOError as e:
        raise AutomatoesError(e)