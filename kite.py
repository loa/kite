#!/usr/bin/env python
# Author: Carl Loa Odin <carlodin@gmail.com>

import ConfigParser, os, sys, subprocess, glob, json
import requests, hmac, base64, hashlib
from stompest.config import StompConfig
from stompest.sync import Stomp

class Kite:
  use_hooks = False
  use_stomp = False

  cloudstack_host      = None
  cloudstack_port      = None
  cloudstack_apikey    = None
  cloudstack_secretkey = None
  cloudstack_apiurl    = None

  stomp_uri      = None
  stomp_login    = None
  stomp_passcode = None
  stomp_queue    = None

  def __init__(self):
    self.read_config()
    self.check_jobs()

  def read_config(self):
    try:
      config = ConfigParser.RawConfigParser()
      config.read("%s/%s" % (os.path.dirname(sys.argv[0]), 'kite.cfg'))

      self.use_hooks = config.get('Kite', 'use_hooks')
      self.use_stomp = config.get('Kite', 'use_stomp')

      self.cloudstack_host      = config.get('Cloudstack', 'host')
      self.cloudstack_port      = config.get('Cloudstack', 'port')
      self.cloudstack_apikey    = config.get('Cloudstack', 'apikey')
      self.cloudstack_secretkey = config.get('Cloudstack', 'secretkey')

      self.stomp_uri      = config.get('Stomp', 'uri')
      self.stomp_login    = config.get('Stomp', 'login')
      self.stomp_passcode = config.get('Stomp', 'passcode')
      self.stomp_queue    = config.get('Stomp', 'queue')

    except Exception as e:
      print "Error in kite.cfg"
      print e
      sys.exit(1)

    # Create url from config settings
    self.apiurl = "http://%s:%s/client/api" % (self.cloudstack_host, self.cloudstack_port)

  def get_jobs(self):
    # Read the list of processed jobs as a json file from kite directory
    try:
      f = open("%s/%s" % (os.path.dirname(sys.argv[0]), 'processed_jobs.json'), 'r')
      jobs = json.load(f)
      f.close()
    except:
      jobs = []

    return jobs

  def save_jobs(self, jobs):
    # Save the list of processed jobs as a json file in kite directory
    f = open("%s/%s" % (os.path.dirname(sys.argv[0]), 'processed_jobs.json'), 'w')
    json.dump(jobs, f)
    f.close()

  def check_jobs(self):
    # Get list of all jobs that already been processed
    prev_processed_jobs = self.get_jobs()

    # New list of all jobs that still appears from api and new processed ones
    processed_jobs = []

    if self.use_stomp:
      stomp_config = StompConfig(self.stomp_uri, login=self.stomp_login, passcode=self.stomp_passcode)
      stomp_client = Stomp(stomp_config)
      stomp_client.connect()

    for job in self.request('listAsyncJobs'):
      # Add job to new processed list
      processed_jobs.append(job['jobid'])

      # Skip job if it's already been processed in previous run
      if job['jobid'] in prev_processed_jobs:
        continue

      if self.use_hooks:
        if job['jobstatus'] == 1:
          # Flatten tree structure
          params = self.parse_dict(job)

          if job['cmd'] == 'com.cloud.api.commands.DestroyVMCmd':
            self.trigger_hooks('vmdestroy', params)

          elif job['cmd'] == 'com.cloud.api.commands.DeployVMCmd':
            self.trigger_hooks('vmdeploy', params)

      if self.use_stomp:
        print "Stomp: %s" % params['jobid']
        stomp_client.send(self.stomp_queue, job)

    if self.use_stomp:
      stomp_client.disconnect()


    # Save list of processed jobs
    self.save_jobs(processed_jobs)

  def request(self, command, params = {}):
    # Set basic params
    params['apikey'] = self.cloudstack_apikey
    params['command'] = command
    params['response'] = 'json'

    # Use fakehost to keep path_url to '/?'
    req = requests.Request('GET', 'http://fakehost', params=params);
    prereq = req.prepare()

    # Create signature with the queries and the secret key
    signature = base64.b64encode(hmac.new(
      self.cloudstack_secretkey,
      msg=prereq.path_url.lower()[2:],
      digestmod=hashlib.sha1
    ).digest())

    # Add signature to params
    params['signature'] = signature

    # Use real Cloudstack api url and read the params
    prereq.prepare_url(self.apiurl, params=params)

    # Use request session to send the prepared
    s = requests.Session()
    resp = s.send(prereq)

    json = resp.json()["%sresponse" % command.lower()]

    if 'errorcode' in json:
      print "%s: %s" % (json['errorcode'], json['errortext'])
      sys.exit(1)

    # Return json response
    for key in json.keys():
      if key != 'count':
        return json[key]

    return {}

  def trigger_hooks(self, hook, params = {}):
    # Get all hooks that we are going to execute
    hooks_dir = "%s/hooks/" % os.path.dirname(__file__)

    # Add environmental variables that kite is run in
    params = dict(dict(os.environ).items() + params.items())

    # Get all files with current hook as a prefix from the hook directory
    for file in glob.glob("%s%s-*" % (hooks_dir, hook)):
      # Make sure file is executable
      if os.access(file, os.X_OK):
        print "Trigger: %s for %s" % (file, params['jobid'])

        # Run hook with job vars as env variables
        subprocess.call([file], env=params, shell=True, executable="/bin/bash")

  def parse_dict(self, init, lkey=''):
    ret = {}
    if isinstance(init, dict):
      for rkey, val in init.items():
        key = lkey+rkey
        if isinstance(val, (dict, list)):
          ret.update(self.parse_dict(val, key+'_'))
        else:
          ret[key] = val
    else:
      for index, val in enumerate(init):
        key = lkey+str(index)
        if isinstance(val, (dict, list)):
          ret.update(self.parse_dict(val, key+'_'))
        else:
          ret[key] = val

    # All values need to be strings when used as environmental vars
    if lkey == '':
      for index, value in ret.items():
        ret[index] = str(value)

    return ret

if __name__ == "__main__":
  Kite()
