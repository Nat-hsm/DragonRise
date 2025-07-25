# DragonRise S3 Deployment Guide

## Overview
Static files are now hosted on AWS S3 at `https://dragonrise-static.s3.us-east-1.amazonaws.com/static/`

## Workflow for Making Changes

### Static Files (CSS, JS, images)
1. Make changes to files in the `/static` directory
2. Run `./sync_static_to_s3.sh` to upload changes to S3
3. (Optional) Purge Cloudflare cache if immediate updates are needed

### Application Code
1. Make changes to Python or template files
2. Run `./deploy_with_s3.sh` to deploy changes to EC2

### Complete Update
To update both static files and application code:
1. Run `./update_all.sh`

## Important URLs
- Application: https://dragonrise.pro
- Static files: https://dragonrise-static.s3.us-east-1.amazonaws.com/static/
- S3 bucket console: https://s3.console.aws.amazon.com/s3/buckets/dragonrise-static

## Troubleshooting
- If static files are not updating, purge the Cloudflare cache
- Check EC2 logs: `sudo tail -f /var/log/dragonrise/error.log`
- Check Nginx logs: `sudo tail -f /var/log/nginx/error.log`