# NSS scoping prepper

RHEL Crypto team internal tool for scoping upstream NSS releases.
**Version:** 1.0

## Install
`pip install -r requirements`

## Config
`cp config.template config`
* add API key to the config.
* you can additionally specify the release.

## Usage
```
./run.py [-r|--release release] [-h|--help]
```
* release in the form `3.16`, `3.16.0`, `3.16.1`. Default: lattest

## Future
* move from searhing phabricator to searching the actual bug for revisions..
