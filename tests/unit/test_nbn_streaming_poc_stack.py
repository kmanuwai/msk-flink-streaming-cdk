import aws_cdk as core
import aws_cdk.assertions as assertions

from nbn_streaming_poc.nbn_streaming_poc_stack import NbnStreamingPocStack

# example tests. To run these tests, uncomment this file along with the example
# resource in nbn_streaming_poc/nbn_streaming_poc_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = NbnStreamingPocStack(app, "nbn-streaming-poc")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
