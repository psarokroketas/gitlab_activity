#!/usr/bin/env python

import json
import datetime
from urllib import urlencode
from argparse import ArgumentParser
import logging
import requests

from aitools.pdb import PdbClient
from aitools.config import PdbConfig, AiConfig
from configrundeckscripts.common import (configure_logging,
                                         get_config,
                                         GITLAB_AI_NAMESPACE_NAME)


config = get_config()

GITLAB_API = 'https://gitlab.cern.ch/api/v4'
headers = {'private-token': config.get('airund', 'gitlab_token')}


def get_ammount_of_commits(project, hours):
    hours_ago = datetime.datetime.now() - datetime.timedelta(hours=hours)
    ammount = 0
    for response in gitlab_paginated_request('projects/%s/repository/commits?with_stats&since=%s'
                                             %(project['id'], hours_ago)):
        if response.status_code == requests.codes.ok:
            ammount += len(response.json())
    return ammount


def parse_arguments():
    parser = ArgumentParser(description="")
    parser.add_argument('hours', type=int,
                        help='Place the hours that passed by since the time you want the results.')
    return parser.parse_args()


def projects_generator():
    for response in gitlab_paginated_request('groups/%s/projects' % GITLAB_AI_NAMESPACE_NAME):
        if response.status_code == requests.codes.ok:
            for project in response.json():
                yield project


def gitlab_paginated_request(url):
    next_page = 1
    url = '%s/%s%spage=' % (GITLAB_API,
                            url,
                            '&' if '?' in url else '?')
    while next_page:
        response = requests.get('%s%s' % (url, next_page), headers=headers)
        yield response
        try:
            next_page = response.headers['x-Next-Page'] or None
        except KeyError:
            next_page = None


def send(document):
    response1 = requests.post('http://monit-metrics.cern.ch:10012',
                              data=json.dumps(document),
                              headers={'Content-Type': 'application/json'})
    if response1.status_code == requests.codes.ok:
        logging.info("Payload sent")
    else:
        logging.error("Problem sending payload")


def main():
    configure_logging()
    config = AiConfig()
    pdb_config = PdbConfig()
    pdb = PdbClient(host='constable.cern.ch', port='9081', timeout='10', deref_alias=True)
    args = parse_arguments()
    word1 = 'hostgroup'
    ammount1 = 0
    ep = "/v3/facts/hostgroup"
    ep2 = "/v3/facts/fename"
    the_certname = {}
    output1 = {}
    output2 = {}

    # Facts endpoint
    #https://docs.puppet.com/puppetdb/2.3/api/query/v3/facts.html#get-v3factsfact-name
    # query format is documented here
    #https://docs.puppet.com/puppetdb/2.3/api/query/v3/query.html
    #  ai-pdb raw /v3/facts/hostgroup --query '["~","value","aiadm"]'

    for project in projects_generator():
        ammount = get_ammount_of_commits(project, args.hours)
        if word1 in project['name']:
            ammount1 = ammount1 + ammount
        y = project['name'].replace("-", " ")
        x = y.split()
        hostgroup_name = x[-1]
        if x[-2] == 'hostgroup':
            query = urlencode({"query": '["~","value","%s"]' %hostgroup_name})
            (code, j) = pdb.raw_request("%s?%s" % (ep, query))
            for i in j:
                the_certname[i['certname']] = ammount
                query2 = urlencode({"query": '["=","certname","%s"]' %i['certname']})
                (code2, j2) = pdb.raw_request("%s?%s" % (ep2, query2))
                for y in j2:
                    output1[i['certname']] = y['value']
    for k, v in the_certname.iteritems():
        for k2, v2 in output1.iteritems():
            if k == k2:
                output2.setdefault(v2, [])
                output2[v2].append(v)
    for k, v in output2.items():
        output2[k] = sum(v)

    #ai-pdb raw /v3/facts/fename --query '["=","certname","aiadm42.cern.ch"]'

    for k, v in output2.iteritems():
        payload = [{
            'producer': 'kpi',
            'type': 'service',
            'serviceid': 'cfg',
            'service_status': 'available',
            str(k): str(v),
        }]
        print payload
        send(payload)


if __name__ == '__main__':
    main()

