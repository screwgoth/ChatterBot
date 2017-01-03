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
from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver
from libcloud.compute.base import NodeImage
import libcloud.security


class DevOpsTasks(LogicAdapter):
    """
    The DevOpsTasks Adapter will parse conversations regarding DevOps and
    attempt to perform tasks accordingly.
    """

    def __init__(self, **kwargs):
        #super(DevOpsTasks, self).__init__(self,**kwargs)
        language = kwargs.get('devops_words_language', 'english')
        self.devops_words = self.get_language_data(language)
        #print self.devops_words
        self.cache = {}

        self.AWS_ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY")
        self.AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
        self.AWS_REGION = os.environ.get("AWS_REGION")
        if not self.AWS_REGION:
            self.AWS_REGION = "us-east-1"
        self.AWS_KEY_NAME = os.environ.get("AWS_KEY_NAME")
        if not self.AWS_KEY_NAME:
            self.AWS_KEY_NAME = "Zymr New"
        self.AWS_IMAGE = os.environ.get("AWS_IMAGE")
        if not self.AWS_IMAGE:
            # The first Amazon Linux AMI 2016.09.1 (HVM)
            self.AWS_IMAGE_ID = "ami-9be6f38c"
        self.AWS_INSTANCE_TYPE = os.environ.get("AWS_INSTANCE_TYPE")
        if not self.AWS_INSTANCE_TYPE:
            self.AWS_INSTANCE_TYPE = "t2.micro"
        self.AWS_SECURITY_GROUP = os.environ.get("AWS_SECURITY_GROUP")
        if not self.AWS_SECURITY_GROUP:
            self.AWS_SECURITY_GROUP = ['default']
        self.AWS_SUBNET = os.environ.get("AWS_SUBNET")
        if not self.AWS_SUBNET:
            self.AWS_SUBNET = "ZYMR"

        self.VSPHERE_USERNAME = os.environ.get("VSPHERE_USERNAME")
        self.VSPHERE_PASSWORD = os.environ.get("VSPHERE_PASSWORD")
        #self.aws_conn = boto.ec2.connect_to_region("us-east-1", aws_access_key_id=self.AWS_ACCESS_KEY, aws_secret_access_key=self.AWS_SECRET_ACCESS_KEY)
        #self.aws_reservations = self.aws_conn.get_all_reservations()

        # This assumes you don't have SSL set up.
        # Note: Code like this poses a security risk (MITM attack) and
        # that's the reason why you should never use it for anything else
        # besides testing. You have been warned.
        libcloud.security.VERIFY_SSL_CERT = False

        self.OPENSTACK_AUTH_USERNAME = os.environ.get("OPENSTACK_AUTH_USERNAME")
        self.OPENSTACK_AUTH_PASSWORD = os.environ.get("OPENSTACK_AUTH_PASSWORD")
        self.OPENSTACK_HOST = os.environ.get("OPENSTACK_HOST")

        acls = get_driver(Provider.EC2)
        self.awsDriver = acls(self.AWS_ACCESS_KEY, self.AWS_SECRET_ACCESS_KEY,
                            region=self.AWS_REGION)
        self.aws_size = self.awsDriver.list_sizes()

        # vcls = get_driver(Provider.VSPHERE)
        # self.vSphereDriver = vcls(host='20.20.4.254', username='root', password='zymr@123')

        ocls = get_driver(Provider.OPENSTACK)
        openstack_auth_url = "http://{}:5000".format(self.OPENSTACK_HOST)
        print "Openstack Auth URL = %s" %(openstack_auth_url)
        self.openstackDriver = ocls(self.OPENSTACK_AUTH_USERNAME, self.OPENSTACK_AUTH_PASSWORD,
                   ex_force_auth_url=openstack_auth_url,
                   ex_force_auth_version='2.0_password',
                   ex_tenant_name="ZCLOUD")

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
                    language, devops_words_data_file_path
                )
            )

    def can_process(self, statement):
        """
        Determines whether it is appropriate for this
        adapter to respond to the user input.
        """
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
        got_cloud = ''
        got_task = ''
        #print input_text
        for cloud in input_text.split():
            if cloud.lower() in self.devops_words['clouds']:
                got_cloud = 1
                # Need to make an exception for VMWare
                if cloud.lower() == "vsphere":
                    cloud = 'VMWare'
                break
            # else:
            #     got_cloud = 0
            #     response = "Sorry, but you have not specified which Cloud to use : {}".format(cloud)

        # if not got_cloud: return got_cloud, Statement(response)
        # got_task = 0
        if got_cloud:
            for task in input_text.split():
                if task.lower() in self.devops_words['tasks']:
                    got_task = 1
                    #print "DevOps Task to \"{}\" VM on \"{}\" successfully executed".format(task, cloud)
                    break

        if got_task:
            func = cloud.lower() + "_" + task.lower()
            #print func
            confidence = 0
            confidence, response = getattr(self, func)(input_text)
            return confidence, Statement(response)
        else:
            response = "I cannot understand what DevOps task you want me to do. Can you try again please?"
            return got_task, Statement(response)

    def instance_list(self, driver):
        listofNodes = driver.list_nodes()
        listofInstances = []
        for node in listofNodes:
            listofInstances.append(node.name)
        return listofInstances

    def aws_count(self, input_text):
        """
        Get the number of running EC2 instances on AWS
        """
        listofVMs = self.instance_list(self.awsDriver)
        response = "Number of AWS instances are : {}".format(len(listofVMs))
        return 1, response

    def aws_many(self, input_text):
        """
        Same as aws_count. Answering to "How many"
        """
        return self.aws_count(input_text)


    def aws_list(self, input_text):
        """
        Get the list of EC2 instances on AWS
        """
        listofVMs = self.instance_list(self.awsDriver)
        vmlist = "\n".join(listofVMs)
        response = "List of VMs on AWS is: \n%s" %(vmlist)
        return 1, response

    def aws_show(self, input_text):
        """
        Same as aws_list()
        """
        return self.aws_list(input_text)

    def aws_start(self, input_text):
        """
        Start an EC2 instance
        """
        response = "Some information was missing. Please provide it in the following format:\nStart AWS VM with name=test-1 type=m3.medium image"
        nodeName = "rasbot-test-2"
        subnets = []
        subnets = self.awsDriver.ex_list_subnets()
        subnet = [s for s in subnets if s.name == self.AWS_SUBNET][0]


        self.aws_size = [s for s in self.aws_size if s.id == self.AWS_INSTANCE_TYPE][0]
        #self.aws_size = NodeSize(id="m1.small", name="", ram=None, disk=None, bandwidth=None, price=None, driver="")

        self.aws_image = NodeImage(id=self.AWS_IMAGE_ID, name=None, driver=self.awsDriver)



        self.awsDriver.create_node(name=nodeName,image=self.aws_image,
                                size=self.aws_size,
                                ex_keyname=self.AWS_KEY_NAME,
                                #ex_securitygroup=self.AWS_SECURITY_GROUP,
                                ex_subnet=subnet,
                                ex_assign_public_ip=False)
        response = "Started EC2 instance"
        return 1, response

    def aws_stop(self, input_text):
        """
        Stop the specified EC2 instance
        """
        response = "Did not find the EC2 instance to stop"
        listofNodes = self.awsDriver.list_nodes()
        for node in listofNodes:
            if node.name in input_text:
                response = "Stopping node : {}".format(node.name)
                self.awsDriver.ex_stop_node(node)

        return 1, response

    def aws_pause(self, input_text):
        """
        Same as aws_stop
        """
        return self.aws_stop(input_text)

    def aws_reboot(self, input_text):
        """
        Reboot the specified EC2 instance
        """
        response = "Did not find the EC2 instance to Reboot"
        listofNodes = self.awsDriver.list_nodes()
        for node in listofNodes:
            if node.name in input_text:
                response = "Rebooting node : {}".format(node.name)
                self.awsDriver.reboot_node(node)

        return 1, response

    def aws_restart(self, input_text):
        """
        Same as aws_reboot
        """
        return self.aws_reboot(input_text)

    def aws_terminate(self, input_text):
        """
        Terminate the specified EC2 instance
        """
        response = "Did not find the EC2 instance to Terminate"
        listofNodes = self.awsDriver.list_nodes()
        for node in listofNodes:
            if node.name in input_text:
                response = "Terminating node : {}".format(node.name)
                self.awsDriver.destroy_node(node)

        return 1, response

    def aws_kill(self, input_text):
        """
        Same as aws_terminate
        """
        return self.aws_terminate(input_text)

    def vmware_count(self, input_text):
        """
        Get the number of running nodes on vSphere
        """
        listofVMs = self.instance_list(self.vSphereDriver)
        response = "Number of vSphere nodes are : {}".format(len(listofVMs))
        return 1, response

    def openstack_count(self, input_text):
        """
        Get the number of running nodes on OpenStack
        """
        print "Counting Openstack VMs"
        listofVMs = self.instance_list(self.openstackDriver)
        response = "Number of Openstack instances are : {}".format(len(listofVMs))
        return 1, response

    def openstack_list(self, input_text):
        """
        Get the list of OpenStack instances
        """
        listofVMs = self.instance_list(self.openstackDriver)
        vmlist = "\n".join(listofVMs)
        response = "List of VMs on Openstack is: \n%s" %(vmlist)
        return 1, response

    def openstack_show(self, input_text):
        """
        Same as openstack_list()
        """
        return self.openstack_list(input_text)
