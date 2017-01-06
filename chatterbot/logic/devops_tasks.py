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
        self.AWS_INSTANCE_NAME = "test-bot-1"
        self.AWS_KEY_NAME = os.environ.get("AWS_KEY_NAME")
        if not self.AWS_KEY_NAME:
            self.AWS_KEY_NAME = "Zymr New"
        self.AWS_IMAGE = os.environ.get("AWS_IMAGE")
        if not self.AWS_IMAGE:
            # The first Amazon Linux AMI 2016.09.1 (HVM)
            # self.AWS_IMAGE_ID = "ami-9be6f38c"
            # The first Ubuntu Server 16.04 LTS (HVM)
            self.AWS_IMAGE_ID = "ami-e13739f6"
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

        vcls = get_driver(Provider.VSPHERE)
        #self.vSphereDriver = vcls(host='https://20.20.4.254', username='root', password='zymr@123')

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
        # print listofNodes
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

    def aws_start(self, input_text):
        """
        Test Task
        """
        response = "Executed the Test Task successfully"
        # print "Default params:\nname = %s\nkeyname = %s\nimage = %s\ntype = %s\nsecurity group = %s\nsubnet = %s"%(self.AWS_INSTANCE_NAME, self.AWS_KEY_NAME,self.AWS_IMAGE_ID,self.AWS_INSTANCE_TYPE,self.AWS_SECURITY_GROUP,self.AWS_SUBNET)

        cloud_params = dict(re.findall(r'(\S+)=(".*?"|\S+)', input_text))
        if cloud_params.has_key('name'):
            self.AWS_INSTANCE_NAME = self.remove_quotes(cloud_params['name'])
            print "Name = %s"%(self.AWS_INSTANCE_NAME)
        else:
            response = "You missed specifying the name of the instance to start. Please specify the name as follows :\nname=\"test-node-1\""
            return 1, response

        if cloud_params.has_key('subnet'):
            self.AWS_SUBNET = self.remove_quotes(cloud_params['subnet'])
            print "Subnet = %s" %(self.AWS_SUBNET)
            subnets = []
            subnets = self.awsDriver.ex_list_subnets()
            subnet = [s for s in subnets if s.name == self.AWS_SUBNET][0]
        else:
            reponse = "You missed specifying the name of the subnet. Please specify the name of a subnet as follows :\nsubnet=\"Production Subnet\""
            return 1, response

        if cloud_params.has_key('type'):
            self.AWS_INSTANCE_TYPE = self.remove_quotes(cloud_params['type'])
            print "Type = %s" %(self.AWS_INSTANCE_TYPE)
            self.aws_size = [s for s in self.aws_size if s.id == self.AWS_INSTANCE_TYPE][0]
            #self.aws_size = NodeSize(id=self.AWS_INSTANCE_TYPE, name="", ram=None, disk=None, bandwidth=None, price=None, driver=self.awsDriver)
        else:
            response = "You missed specifying the name of the Instance type to start. Please specify an Instance type as follows :\ntype=t2.micro"
            return 1, response

        if cloud_params.has_key('image'):
            self.AWS_IMAGE_ID = self.remove_quotes(cloud_params['image'])
            print "Image = %s" %(self.AWS_IMAGE_ID)
            self.aws_image = NodeImage(id=self.AWS_IMAGE_ID, name=None, driver=self.awsDriver)
        else:
            response = "You missed specifying the AMI ID of the instnce to start. Please specify an AWS Image ID as follows :\nimage=ami-e13739f6"
            return 1, response

        if cloud_params.has_key('keyname'):
            self.AWS_KEY_NAME = self.remove_quotes(cloud_params['keyname'])
            print "Keyname = %s" %(self.AWS_KEY_NAME)
        else:
            response = "You missed specifying the name of a Keypair. Please specify the name of a Keypair as follows :\nkeyname=\"Zymr New\""
            return 1, response

        if cloud_params.has_key('securitygroup'):
            self.AWS_SECURITY_GROUP = []
            self.AWS_SECURITY_GROUP.append(self.remove_quotes(cloud_params['securitygroup']))
            print "Security Group = %s" %(self.AWS_SECURITY_GROUP)

        self.awsDriver.create_node(name=self.AWS_INSTANCE_NAME,image=self.aws_image,
                                size=self.aws_size,
                                ex_keyname=self.AWS_KEY_NAME,
                                #ex_securitygroup=self.AWS_SECURITY_GROUP,
                                ex_subnet=subnet,
                                ex_assign_public_ip=False)
        response = "Starting EC2 instance. It should be up in 3 minutes"

        return 1, response

    def remove_quotes(self, string):
        if string.startswith('"') and string.endswith('"'):
            string = string[1:-1]
        return string


    def vmware_count(self, input_text):
        """
        Get the number of running nodes on vSphere
        """
        listofVMs = self.instance_list(self.vSphereDriver)
        response = "Number of vSphere nodes are : {}".format(len(listofVMs))
        return 1, response

    def vmware_test(self, input_text):
        """
        Test Task
        """
        response = "Executed the Test Task successfully"
        print "Test Task"

        return 1, response

    def openstack_count(self, input_text):
        """
        Get the number of running nodes on OpenStack
        """
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

    def openstack_start(self, input_text):
        """
        Start an OpenStack instance
        """
        response = "Some information was missing. Please provide it in the following format:\nStart Openstack VM with name=test-1 type=m3.medium image"
        nodeName = "rasbot-test-3"
        subnets = []
        subnets = self.openstackDriver.ex_list_subnets()
        subnet = [s for s in subnets if s.name == self.OPENSTACK_SUBNET][0]


        self.openstack_size = [s for s in self.aws_size if s.id == self.OPENSTACK_INSTANCE_TYPE][0]
        #self.aws_size = NodeSize(id="m1.small", name="", ram=None, disk=None, bandwidth=None, price=None, driver="")

        self.openstack_image = NodeImage(id=self.OPENSTACK_IMAGE_ID, name=None, driver=self.openstackDriver)



        self.awsDriver.create_node(name=nodeName,image=self.openstack_image,
                                size=self.openstack_size,
                                ex_keyname=self.OPENSTACK_KEY_NAME,
                                #ex_securitygroup=self.OPENSTACK_SECURITY_GROUP,
                                ex_subnet=subnet,
                                ex_assign_public_ip=False)
        response = "Started OpenStack instance"
        return 1, response

    def openstack_stop(self, input_text):
        """
        Stop the specified Openstack instance
        """
        response = "Did not find the Openstack instance to stop"
        listofNodes = self.openstackDriver.list_nodes()
        for node in listofNodes:
            if node.name in input_text:
                response = "Stopping node : {}".format(node.name)
                self.openstackDriver.ex_stop_node(node)

        return 1, response

    def openstack_pause(self, input_text):
        """
        Same as openstack_stop
        """
        return self.openstack_stop(input_text)

    def openstack_reboot(self, input_text):
        """
        Reboot the specified OpenStack instance
        """
        response = "Did not find the OpenStack instance to Reboot"
        listofNodes = self.openstackDriver.list_nodes()
        for node in listofNodes:
            if node.name in input_text:
                response = "Rebooting node : {}".format(node.name)
                self.openstackDriver.reboot_node(node)

        return 1, response

    def openstack_restart(self, input_text):
        """
        Same as openstack_reboot
        """
        return self.openstack_reboot(input_text)

    def openstack_terminate(self, input_text):
        """
        Terminate the specified OpenStack instance
        """
        response = "Did not find the OpenStack instance to Terminate"
        listofNodes = self.openstackDriver.list_nodes()
        for node in listofNodes:
            if node.name in input_text:
                response = "Terminating node : {}".format(node.name)
                self.openstackDriver.destroy_node(node)

        return 1, response

    def openstack_kill(self, input_text):
        """
        Same as openstack_terminate
        """
        return self.openstack_terminate(input_text)

    def openstack_test(self, input_text):
        """
        Test Task
        """
        response = "Executed the Test Task successfully"
        print "Test Task"

        return 1, response
