# DragonRise - AWS Bedrock Setup Guide

## AWS Bedrock Configuration

To use the image analysis feature in DragonRise, you need to properly configure AWS Bedrock access:

1. **Enable Model Access**:
   - Log in to the AWS Console
   - Navigate to Amazon Bedrock
   - Go to "Model access" in the left sidebar
   - Request access to at least one of these models:
     - Amazon Titan Text models
     - Claude Instant
     - Claude 3 Haiku (for image analysis)
   - Wait for access approval (usually immediate)

2. **Update IAM Permissions**:
   - Your IAM user needs these permissions:
     ```json
     {
         "Version": "2012-10-17",
         "Statement": [
             {
                 "Effect": "Allow",
                 "Action": [
                     "bedrock:ListFoundationModels",
                     "bedrock:GetFoundationModel"
                 ],
                 "Resource": "*"
             },
             {
                 "Effect": "Allow",
                 "Action": [
                     "bedrock:InvokeModel"
                 ],
                 "Resource": [
                     "arn:aws:bedrock:*:*:foundation-model/*"
                 ]
             }
         ]
     }
     ```

3. **Test Your Configuration**:
   - Run the test script: `python test_bedrock.py`
   - Verify you can list models and invoke at least one model

## Troubleshooting

If you encounter an "AccessDeniedException" when invoking models:

1. Check that you've enabled the model in "Model access"
2. Verify your IAM policy includes `bedrock:InvokeModel` permission
3. Look for any explicit deny statements in your IAM policies
4. Try using a different model (Amazon Titan models are often enabled by default)

## Environment Variables

Make sure these environment variables are set:

```
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1
```

You can set these in your `.env` file or directly in your environment.