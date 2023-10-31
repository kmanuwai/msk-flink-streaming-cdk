# Note: MSK cluster takes almost 40 mins to deploy

from aws_cdk import (
    # Duration,
    Stack,
    # aws_sqs as sqs,
    aws_ec2 as ec2,
    aws_msk as msk,
    aws_s3 as s3,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_events_targets as targets,
    aws_events as events,
    Duration
)
from constructs import Construct

class NbnStreamingPocStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(self, 
            "msk-vpc",
            #cidr=172.1.0.0/16,
            nat_gateways=1,
            )
            
        #TODO: create cluster configuration with auto.create.topics.enable=true
        # config_file = open('cluster_config.txt', 'r')
        # server_properties = config_file.read()
        # cfn_configuration = msk.CfnConfiguration(self, "MyCfnConfiguration",
        #     name="MSKConfig",
        #     server_properties=server_properties
        # )

        
        msk_cluster = msk.CfnCluster(
            self,
            "msk-cluster",
            cluster_name='cdk-test',#stack_name+'msk-cluster',
            number_of_broker_nodes=len(vpc.private_subnets),
            kafka_version='2.3.1',
            broker_node_group_info=msk.CfnCluster.BrokerNodeGroupInfoProperty(
                instance_type="kafka.m5.large",
                client_subnets=[
                    subnet.subnet_id
                    for subnet
                    in vpc.private_subnets],
            ),
            encryption_info = msk.CfnCluster.EncryptionInfoProperty(
                encryption_in_transit=msk.CfnCluster.EncryptionInTransitProperty(
                    client_broker="PLAINTEXT",
                    in_cluster=False
                )
            ),
            # configuration_info=msk.CfnCluster.ConfigurationInfoProperty(
            #     arn=cfn_configuration.attr_arn,
            #     revision=1
            # ),
        )
        

    
        # LAMBDA FUNCTIONS
        # IAM Role for all functions
        lambda_role = iam.Role(
            self,
            "lambda-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            # TODO: Tighten up these policies!
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("AmazonMSKFullAccess"),
                               iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2FullAccess"),
                               iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSNSFullAccess"),
                               ]
        )
            
        
        # Producer Function
        # TODO change to using layers for kafka libraries 
        lambdaFn = lambda_.Function(
            self, "kfpLambdaStreamProducer",
            code=lambda_.Code.from_asset("./lambda-functions"),
            handler="kfpLambdaStreamProducer.lambda_handler",
            timeout=Duration.seconds(300),
            runtime=lambda_.Runtime.PYTHON_3_8,
            environment={'topicName':'kfp_sensor_topic',
                         'mskClusterArn':msk_cluster.attr_arn},
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType('PRIVATE_WITH_EGRESS')),
            role=lambda_role,
        )

        # Run every minute
        # See https://docs.aws.amazon.com/lambda/latest/dg/tutorial-scheduled-events-schedule-expressions.html
        rule = events.Rule(
            self, "scheduledEvent",
            schedule=events.Schedule.rate(Duration.seconds(300)),
        )
        rule.add_target(targets.LambdaFunction(lambdaFn))
    
        
        # Bucket where output of Apache Flink is stored 
        output_bucket = s3.Bucket(
            self,
            "output-bucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )
        

        
