# cli-erbulk
Example plugin for Akamai Command Line Utility to manage bulk unique redirects (>100k) by using multiple cloudlet policies

Bulk redirects can be used to manage lots of **unique** redirects by using multiple redirect policies and select the right policy based on the hash of the path of the request.

This works for unique redirects only, no wildcards, no regular expressions.

## Workflow
1. Create a CSV file with all redirects. The CSV has to contain two or three columns: source-url-path,target-url-path [, 301|302]
2.  Create a basic _SHARED_ edge redirect policy within the Akamai Control Center in the right group. This policy should contain all non-unique redirects and will be the start of every generated redirect policy
3. Parse th CSV into multiple redirect policies using the CLI. By default 32 policies will be created
4. Activate the redirect policies using the CLI in staging
5. Create a property manager version that needs to be updated in the property manager
6. Update the propery manager properties that use the redirect policy using the CLI
7. Refresh the propery manager version and verify the generated rule. Add matches if required and solve any inconsistencies
7. Activate the property manager version in staging and test
8. Activate the redirect policies in production (using the CLI) and the property manager version in production (using the property manager (or PM CLI))

## Configuration file
Intermediate results will be stored in a con configuration file. The default name for the configurationfile is _base-policy_**.json**

## Examples

### Check the syntax
```bash
%  akamai erbulk --help
```

### Parse a CSV file
```bash
%  akamai erbulk erbulk_test --parse erbulk.csv 
```

### Activate the edgeredirector policies on staging or production
```bash
%  akamai erbulk erbulk_test --activate STAGING
%  akamai erbulk erbulk_test --activate PRODUCTION
```

### Add or update the ER-bulk rule 
```bash
%  akamai erbulk erbulk_test --update-property www.example.com
```
Note: _Use stderr to catch all the warnings_

## Known limitations
- Works for unique matches only
- Match on hostname, database scheme and query paramters not supported
- No proper error cheching. If you get a stack trace, consult the source code
- Not tested 

## Run within your python environment
For devlopment purpose you can just run this in your own environment
```bash
git clone https://github.com/ericdebeij/cli-erbulk
cd cli-erbulk
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
python3 bin/akamai-erbulk.py --help
```

## Akamai CLI Install
akamai install is no longer able to install a custom plugin. To install the plugin manually you have to take the following manual steps (example steps when you are on a Mac):
```bash
akamai
cd ~/.akamai-cli
mkdir -p src
cd src
git clone https://github.com/ericdebeij/cli-erbulk
cd cli-erbulk
mkdir -p ../../venv
python3 -m venv ../../venv/cli-erbulk
source ../../venv/cli-erbulk/bin/activate
pip3 install -r requirements.txt
cd
akamai erbulk --help

# PS: in the past it was simple.
#%  akamai install https://github.com/ericdebeij/cli-erbulk
```

## Requirements
* Python 3.10+
* Modules as defined in requirements.txt

## Warranty
This is sample software. As such this software comes with absolutely no warranty. The software can be used to show how to do bulk redirects with edge redirector.

## Command line
```bash
% akamai erbulk policy [options]
```

## Usage
```bash
% akamai erbulk --help

usage: akamai-erbulk.py [-h] [--parse CSV] [--delimiter ,] [--activate NETWORK [NETWORK ...]] [--update-property PROPERTY [PROPERTY ...]] [--config JSON] [--buckets N] [--edgerc EDGERC] [--section SECTION] [--account ACCOUNT]
                        policy

Bulk edge redirector

positional arguments:
  policy                basename of the policy

options:
  -h, --help            show this help message and exit
  --parse CSV           parse CSV and generate edge-redirect policies
  --delimiter ,         CSV delimiter
  --activate NETWORK [NETWORK ...]
                        push edge-redirect policies to STAGING and PRODUCTION
  --update-property PROPERTY [PROPERTY ...]
                        properties to be updated (last version is used and should be editable)
  --config JSON         configuration file, defaults to ./POLICY.json
  --buckets N           number of buckets, defaults to number in the config or 32
  --edgerc EDGERC       edgerc config path passed to executed commands, defaults to ~/.edgerc
  --section SECTION     edgerc section name passed to executed commands, defaults to 'default'
  --account ACCOUNT     account identification (only if multiple accounts can be used)
```

# Contribution

By submitting a contribution (the “Contribution”) to this project, and for good and valuable consideration, the receipt and sufficiency of which are hereby acknowledged, you (the “Assignor”) irrevocably convey, transfer, and assign the Contribution to the owner of the repository (the “Assignee”), and the Assignee hereby accepts, all of your right, title, and interest in and to the Contribution along with all associated copyrights, copyright registrations, and/or applications for registration and all issuances, extensions and renewals thereof (collectively, the “Assigned Copyrights”). You also assign all of your rights of any kind whatsoever accruing under the Assigned Copyrights provided by applicable law of any jurisdiction, by international treaties and conventions and otherwise throughout the world. 

# Notice

Copyright 2021 – Akamai Technologies, Inc.
 
All works contained in this repository, excepting those explicitly otherwise labeled, are the property of Akamai Technologies, Inc.

