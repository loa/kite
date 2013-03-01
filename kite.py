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
    for job in self.request('listAsyncJobs', {}):
      for key in job.keys():
        print "%s: %s" % (key, job[key])
      break

  def request(self, command, params):
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

    # Return json response
    for key in resp.json()["%sresponse" % command.lower()].keys():
      if key != 'count':
        return resp.json()["%sresponse" % command.lower()][key]

    return None

  def trigger_hooks(self, hook, params = {}):
    hooks_dir = "%s/hooks/" % os.path.dirname(__file__)

    # Get all files with current hook as a prefix from the hook directory
    for file in glob.glob("%s%s-*" % (hooks_dir, hook)):
      print "Trigger: %s" % file

      # Run hook with job vars as env variables
      subprocess.call([file], env=params, shell=True, executable="/bin/bash")

if __name__ == "__main__":
  Kite()
