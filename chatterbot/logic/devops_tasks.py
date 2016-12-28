from __future__ import unicode_literals
from chatterbot.logic import LogicAdapter
from chatterbot.conversation import Statement
import re
import os
import json
import boto.ec2
import atexit
import ssl
from pyVim import connect
from pyVmomi import vmodl
from pyVmomi import vim


class DevOpsTasks(LogicAdapter):
    """
    The DevOpsTasks Adapter will parse conversations regarding DevOps and
    attempt to perform tasks accordingly.
    """

    def __init__(self, **kwargs):
        #super(DevOpsTasks, self).__init__(self,**kwargs)
        language = kwargs.get('devops_words_language', 'english')
        self.devops_words = self.get_language_data(language)
        print self.devops_words
        self.cache = {}

        self.AWS_ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY")
        self.AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
        self.VSPHERE_USERNAME = os.environ.get("VSPHERE_USERNAME")
        self.VSPHERE_PASSWORD = os.environ.get("VSPHERE_PASSWORD")
        self.aws_conn = boto.ec2.connect_to_region("us-east-1", aws_access_key_id=self.AWS_ACCESS_KEY, aws_secret_access_key=self.AWS_SECRET_ACCESS_KEY)
        self.aws_reservations = self.aws_conn.get_all_reservations()

    def get_language_data(self, language):
        """
        Load language-specific data
        """
        from chatterbot.corpus import Corpus

        corpus = Corpus()

        devops_words_data_file_path = corpus.get_file_path(
            'chatterbot.corpus.{}.devops_words'.format(language),
            extension='json'
        )

        try:
            with open(devops_words_data_file_path) as data:
                return json.load(data)
        except IOError:
            raise self.UnrecognizedLanguageException(
                'A devops_words data file was not found for `{}` at `{}`.'.format(
                    language, math_words_data_file_path
                )
            )

    # def can_process(self, statement):
    #     """
    #     Determines whether it is appropriate for this
    #     adapter to respond to the user input.
    #     """
        confidence, response = self.process(statement)
        self.cache[statement.text] = (confidence, response)
        return confidence == 1

    def process(self, statement):
        """
        Check if the statemnt contains any DevOps words and if so, execute the task
        """
        input_text = statement.text

        # Use the result cached by the process method if it exists
        if input_text in self.cache:
            cached_result = self.cache[input_text]
            self.cache = {}
            return cached_result

        response = ''
        print input_text
        for cloud in input_text.split():
            if cloud in self.devops_words['clouds']:
                response = "DevOps Cloud successfully executed"
                print "Got Cloud: {}".format(cloud)
                got_cloud = 1
                break
            else:
                got_cloud = 0
                response = "Sorry, but you have not specified which Cloud to use : {}".format(cloud)

        if not got_cloud: return got_cloud, Statement(response)
        got_task = 0
        if got_cloud:
            for task in input_text.split():
                if task in self.devops_words['tasks']:
                    got_task = 1
                    print "DevOps Task to \"{}\" VM on \"{}\" successfully executed".format(task, cloud)
                    break



        if got_task:
            print "Creating function"
            func = cloud + "_" + task
            print func
            confidence = 0
            confidence, response = getattr(self, func)()
            return confidence, Statement(response)
        else:
            response = "DevOps Task could not be executed"
            return got_task, Statement(response)


    def aws_count(self):
        print "Counting AWS VMs"
        count = 0
        for reservation in self.aws_reservations:
            instances = reservation.instances

            for instance in instances:
                if instance.state == 'running':
                    count += 1
                    tags = instance.tags
                    instanceName = 'Default'
                    if 'Name' in tags:
                        instanceName = tags['Name']
        response = "Number of AWS instances are : {}".format(count)
        return 1, response

    def aws_list(self):
        listofVMs = []
        for reservation in self.aws_reservations:
            instances = reservation.instances

            for instance in instances:
                if instance.state == 'running':
                    tags = instance.tags
                    instanceName = 'Default'
                    if 'Name' in tags:
                        instanceName = tags['Name']
                        listofVMs.append(instanceName)
        vmlist = "\n".join(listofVMs)
        response = "List of VMs on AWS is: \n%s" %(vmlist)
        return 1, response
