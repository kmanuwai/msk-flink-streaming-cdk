# Note: MSK cluster takes almost 40 mins to deploy
# pip install aws-cdk.aws_kinesisanalytics_flink_alpha
from aws_cdk import (
    # Duration,
    Stack,
    RemovalPolicy,
    Fn,
    # aws_sqs as sqs,
    aws_ec2 as ec2,
    aws_msk as msk,
    aws_s3 as s3,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_events_targets as targets,
    aws_events as events,
    Duration,
    aws_s3_assets as assets,
    aws_s3_deployment as s3deployment,
    aws_kinesisanalyticsv2 as kinesisanalyticsv2,
    aws_logs as logs,
)
from constructs import Construct
#import aws_cdk.aws_kinesisanalytics_flink_alpha as flink

class NbnStreamingPocStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(self, 
            "msk-vpc",
            #cidr=172.1.0.0/16,
            nat_gateways=1,
            )
            
        # Security Group that allows all traffic within itself 
        all_sg = ec2.SecurityGroup(self,
            "all_sg", 
            vpc=vpc,
            allow_all_outbound=True,
        )
            
        all_sg.add_ingress_rule(
          all_sg,
          ec2.Port.all_traffic(), # TODO: Change to port just needed by MSK
          "allow all traffic in SG",
        )

        
        # Load cluster configurations from file     
        config_file = open('./nbn_streaming_poc/cluster_config', 'r')
        server_properties = config_file.read()
        cfn_configuration = msk.CfnConfiguration(self, "MyCfnConfiguration",
            name="MSKConfig",
            server_properties=server_properties
        )

        # MSK Cluster
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
                security_groups=[all_sg.security_group_id], 
            ),
            encryption_info = msk.CfnCluster.EncryptionInfoProperty(
                encryption_in_transit=msk.CfnCluster.EncryptionInTransitProperty(
                    client_broker="PLAINTEXT",
                    in_cluster=False
                )
            ),
            configuration_info=msk.CfnCluster.ConfigurationInfoProperty(
                arn=cfn_configuration.attr_arn,
                revision=1
            ),
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
                               iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
                               ],
        )
            
        
        # Producer Function
        # TODO change to using layers for kafka libraries 
        lambdaFn = lambda_.Function(
            self, "kfpLambdaStreamProducer",
            code=lambda_.Code.from_asset("./lambda-functions"),
            handler="kfpLambdaStreamProducer.lambda_handler",
            timeout=Duration.seconds(500),
            runtime=lambda_.Runtime.PYTHON_3_8,
            environment={'topicName':'kfp_sensor_topic',
                         'mskClusterArn':msk_cluster.attr_arn},
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType('PRIVATE_WITH_EGRESS')),
            role=lambda_role,
            security_groups=[all_sg],# TODO: tighten up security group 
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
        
        # Bucket where output of Apache Flink is stored 
        flink_code_bucket = s3.Bucket(
            self,
            "flink-code-bucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy = RemovalPolicy.DESTROY
        )

        # Upload Flink files to an S3 bucket
        # flink_app_code_asset = assets.Asset(self, "flink_app_code",
        #     path="./PythonKafkaSink/",
        # )
            
        flink_app_code_zip = s3deployment.BucketDeployment(self, "flink_app_code_zip",
            sources=[s3deployment.Source.asset("./PythonKafkaSink/PythonKafkaSink.zip")],
            destination_bucket=flink_code_bucket,
            extract=False
            
            
        )
            
        # Apache Flink Role
        # TODO CHANGE FROM ADMIN ACCESS
        flink_role = iam.Role(self, "Flink_App_Role",
          assumed_by=iam.ServicePrincipal("kinesisanalytics.amazonaws.com"),
          managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")]
          )
          
         
        
        # APACHE FLINK
        apache_flink_app = kinesisanalyticsv2.CfnApplication(self, "ApacheFlinkApp",
            runtime_environment="FLINK-1_11",
            service_execution_role=flink_role.role_arn,
        
            # the properties below are optional
            application_configuration=kinesisanalyticsv2.CfnApplication.ApplicationConfigurationProperty(
                application_code_configuration=kinesisanalyticsv2.CfnApplication.ApplicationCodeConfigurationProperty(
                    code_content=kinesisanalyticsv2.CfnApplication.CodeContentProperty(
                        s3_content_location=kinesisanalyticsv2.CfnApplication.S3ContentLocationProperty(
                            bucket_arn=flink_code_bucket.bucket_arn, #"arn:aws:s3:::"+flink_app_code_asset.s3_bucket_name,
                            file_key=Fn.select(0, flink_app_code_zip.object_keys) #flink_app_code_asset.s3_object_key,#"PythonKafkaSink.zip" 
        
                    
                        ),
                    ),
                    code_content_type="ZIPFILE"
                ),
                application_snapshot_configuration=kinesisanalyticsv2.CfnApplication.ApplicationSnapshotConfigurationProperty(
                    snapshots_enabled=False
                ),
                environment_properties=kinesisanalyticsv2.CfnApplication.EnvironmentPropertiesProperty(
                    property_groups=[
                        kinesisanalyticsv2.CfnApplication.PropertyGroupProperty(
                            property_group_id="kinesis.analytics.flink.run.options",
                            property_map={
                                "python" : "PythonKafkaSink/main.py", 
                                "jarfile" : "PythonKafkaSink/lib/flink-sql-connector-kafka_2.11-1.11.2.jar" 
                            }
                            ),
                        kinesisanalyticsv2.CfnApplication.PropertyGroupProperty(
                            property_group_id="producer.config.0",
                            property_map={
                                "input.topic.name" : "kfp_sensor_topic",
                                "bootstrap.servers": "replace msk brokers list here" # TODO: fill with details
                            }
                        ),
                        kinesisanalyticsv2.CfnApplication.PropertyGroupProperty(
                            property_group_id="consumer.config.0",
                            property_map={
                                "output.topic.name": "kfp_sns_topic",
                                "output.s3.bucket": output_bucket.bucket_name
                            }
                        ),
                    ]
                )
            )
        )
        
        # Logging for Apache Flink
        apache_log_group = logs.LogGroup(self, "ApacheFlinkLogGroup")
        
        apache_log_stream = logs.LogStream(self, "ApacheFlinkLogStream",
            log_group=apache_log_group
            )

        
        apache_flink_cloud_watch_logging_option = kinesisanalyticsv2.CfnApplicationCloudWatchLoggingOption(self, "ApacheFlinkAppCloudWatchLoggingOption",
            application_name=apache_flink_app.get_att("ApplicationName").to_string(),
            cloud_watch_logging_option=kinesisanalyticsv2.CfnApplicationCloudWatchLoggingOption.CloudWatchLoggingOptionProperty(
                log_stream_arn="arn:aws:logs:"+self.region+":"+self.account+":log-group:"+ apache_log_group.log_group_name+":log-stream:"+apache_log_stream.log_stream_name
                ##Fn.get_att(apache_log_stream.logicalId, "Arn").to_string()
            )
        )
        
        apache_flink_cloud_watch_logging_option.add_dependency(apache_log_stream.node.default_child)
        apache_flink_cloud_watch_logging_option.add_dependency(apache_flink_app)
        

        
        
        

        
