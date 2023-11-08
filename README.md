
# Real-Time Streaming with Amazon Managed Apache Kafka and Flink 

Based on: https://aws.amazon.com/blogs/big-data/build-a-real-time-streaming-application-using-apache-flink-python-api-with-amazon-kinesis-data-analytics/

To run: 
1. Clone the GitHub Repository. 
Note: You will need to authenticate. I.e. utilising GitHub CLI or Personal Access Tokens (https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
```
git clone https://github.com/kmanuwai/msk-flink-streaming.git
```

2. Change into the cloned directory:
```
cd msk-flink-streaming
```

3. Install the required dependencies:
```
pip install -r requirements.txt
```

4. (Optional) Bootstrap AWS Account for CDK:
```
cdk bootstrap
```

5. Deploy the stack:

```
cdk deploy
```

