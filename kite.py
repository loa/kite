#!/usr/bin/env python

import ConfigParser, os, sys, subprocess, glob
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

  def check_jobs(self):
    for job in self.request('listAsyncJobs'):
      if job['jobstatus'] == 1:
        cmd = job['cmd']

        # Flatten tree structure
        job = self.parse_dict(job['jobresult']['virtualmachine'])

        # All values need to be strings
        for index, value in job.items():
          job[index] = str(value)

        if cmd == 'com.cloud.api.commands.DestroyVMCmd':
          self.trigger_hooks('vmdestroy', job)

        if cmd == 'com.cloud.api.commands.CreateVMCmd':
          self.trigger_hooks('vmcreate', job)

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
    hooks_dir = "%s/hooks/" % os.path.dirname(__file__)

    # Get all files with current hook as a prefix from the hook directory
    for file in glob.glob("%s%s-*" % (hooks_dir, hook)):
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

    return ret

if __name__ == "__main__":
  Kite()
