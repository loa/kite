#!/usr/bin/env python
# Author: Carl Loa Odin <carlodin@gmail.com>

import ConfigParser, os, sys, subprocess, glob, json
import requests, hmac, base64, hashlib

class Kite:
  host = None
  port = None
  apikey = None
  secretkey = None
  apiurl = None

  def __init__(self):
    self.read_config()
    self.check_jobs()

  def read_config(self):
    try:
      config = ConfigParser.RawConfigParser()
      config.read("%s/%s" % (os.path.dirname(sys.argv[0]), 'kite.cfg'))

      self.host = config.get('Cloudstack', 'host')
      self.port = config.get('Cloudstack', 'port')
      self.apikey = config.get('Cloudstack', 'apikey')
      self.secretkey = config.get('Cloudstack', 'secretkey')
    except Exception as e:
      print "Error in kite.cfg"
      print e
      sys.exit(1)

    # Create url from config settings
    self.apiurl = "http://%s:%s/client/api" % (self.host, self.port)

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

    for job in self.request('listAsyncJobs'):
      # Add job to new processed list
      processed_jobs.append(job['jobid'])

      # Skip job if it's already been processed in previous run
      if job['jobid'] in prev_processed_jobs:
        continue

      if job['jobstatus'] == 1:
        # Flatten tree structure
        params = self.parse_dict(job['jobresult'])

        if job['cmd'] == 'com.cloud.api.commands.DestroyVMCmd':
          self.trigger_hooks('vmdestroy', params)

        elif job['cmd'] == 'com.cloud.api.commands.DeployVMCmd':
          self.trigger_hooks('vmdeploy', params)

    # Save list of processed jobs
    self.save_jobs(processed_jobs)

  def request(self, command, params = {}):
    # Set basic params
    params['apikey'] = self.apikey
    params['command'] = command
    params['response'] = 'json'

    # Use fakehost to keep path_url to '/?'
    req = requests.Request('GET', 'http://fakehost', params=params);
    prereq = req.prepare()

    # Create signature with the queries and the secret key
    signature = base64.b64encode(hmac.new(
      self.secretkey,
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
        print "Trigger: %s" % file

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
