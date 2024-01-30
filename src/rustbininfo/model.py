import json
import pathlib
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set

import requests
import semver
from packaging.version import Version, parse
from pydantic import BaseModel

from .exceptions import InvalidVersionError
from .logger import logger as log
from .util import get_default_dest_dir


class Config(BaseModel):
    # target: pathlib.Path
    ...


def _urljoin(base: str, *parts: str) -> str:
    for part in filter(None, parts):
        base = "{}/{}".format(base.rstrip("/"), part.lstrip("/"))
    return base


class Crate(BaseModel):
    name: str
    version: str
    features: List[str] = []
    _available_versions: List[str] = []
    _available_features: List[str] = []
    _api_base_url: str = "https://crates.io/"
    _version_info: dict = None
    _fast_load: bool = True

    @classmethod
    def from_depstring(cls, dep_str: str, fast_load=True) -> "Crate":
        try:
            name, version = dep_str.rsplit("-", 1)
            return cls(
                name=name,
                version=str(semver.Version.parse(version)),
                _fast_load=fast_load,
            )

        except:
            name, version, _ = dep_str.rsplit("-", 2)
            return cls(
                name=name,
                version=str(semver.Version.parse(version)),
                _fast_load=fast_load,
            )

    def model_post_init(self, __context) -> None:
        if not self._fast_load:
            self._get_metadata()

    def _get_metadata(self):
        log.debug(f"Downloading metadata for {self.name}")
        uri = _urljoin(self._api_base_url, *["api", "v1", "crates", self.name])
        headers = {"User-Agent": "rustbininfo (https://github.com/N0fix/rustbininfo)"}
        res = requests.get(uri, timeout=20, headers=headers)
        result = json.loads(res.text)
        for version in result["versions"]:
            self._available_versions.append(version["num"])
            if version["num"] == self.version:
                self._version_info = version
                for feature in version["features"]:
                    self.features.append(feature)

        if self.version not in self._available_versions:
            raise InvalidVersionError

        assert self._version_info is not None

    def download(self, destination_directory: Optional[Path] = None) -> Path:
        log.debug(f"Downloading crate {self.name}")

        if len(self._available_versions) == 0:
            self._get_metadata()

        if destination_directory is None:
            destination_directory = get_default_dest_dir()

        uri = _urljoin(self._api_base_url, *self._version_info["dl_path"].split("/"))
        headers = {"User-Agent": "rustbininfo (https://github.com/N0fix/rustbininfo)"}
        res = requests.get(uri, timeout=20, headers=headers)
        assert res.status_code == 200

        result_file = destination_directory.joinpath(f"{self}.tar.gz")
        open(result_file, "wb+").write(res.content)

        return result_file

    def __str__(self):
        return f"{self.name}-{self.version}"

    def __hash__(self):
        return hash((self.name, self.version))


class CompilationCtx(BaseModel):
    profile: str = "release"
    template: Optional[Dict] = {
        "lib": {"crate-type": ["dylib"]},
        "profile": {
            "release": {"debug": 2, "panic": "abort"},  # Usefull for no-std crates
            "dev": {"debug": 2, "panic": "abort"},  # Usefull for no-std crates
        },
    }
    lib: bool = True
    env: Optional[dict] = {}  # Additional env variable to use compile time