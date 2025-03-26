---
layout: post
title:  "Customize & Schedule and Your Report with New Relic Reporting"
author: Andi
categories: [ New Relic, Tutorial ]
image: assets/images/nr-report-csv.jpg
tags: [featured]
---

New Relic Reports is a report generation and automation framework for New Relic.

### Report Generation

The New Relic Reports engine provides support for generating reports in several ways.

Template Reports

Template reports provide a mechanism for building custom reports using templates. Templates are text-based, user-defined documents that can contain both content and logic. Templates are processed when a template report is run to produce text-based output. Special bits of logic called extensions are provided that make it easy to use New Relic data in template reports. By default, the output is rendered in a browser to produce PDF output, but it is just as easy to disable rendering and deliver the template output in a variety of ways.

Dashboard Reports

Dashboard reports use Nerdgraph to collect snapshot URLs from one or more user specified dashboard GUIDs. Snapshot URLs are downloaded as PDFs. When more than one dashboard is specified, the PDFs can optionally be concatenated into a single PDF.

Query Reports

Query reports provide a mechanism to export the results of running a NRQL query by simply specifying a query and one or more account IDs to run the query against. No additional configuration is required. By default, query results are exported to CSV but can also be exported as HTML or JSON.

### Report Delivery

A variety of mechanisms are supported for delivering report output. These mechanisms are referred to as channels. The following types of channels are supported.

- File: Report output is saved to a file and copied to a destination directory on the local filesystem. Mostly meant for development and testing purposes.
- Email: Report output is included inline or as attachments to an email using a user defined email template and sent via SMTP.
- S3: Report output is saved to a file and uploaded to an S3 bucket.
- Slack: Report output is posted to a Slack channel via a Slack webhook.
- Webhook: Report output is posted to a custom Webhook.
  

### Running Reports

There are several ways to run reports using the reporting engine.

- Packaged as a Docker image
- Packaged as an AWS Lambda function
- Using the command line interface (CLI)

You can find the documentation here : https://github.com/newrelic/nr-reports

### Example: Exporting Infrastructure Data  into CSV

The following example is exporting infrastructure information such as average CPU percentage, average memory consumption, and average disk used percentage. The process will produce a csv file in a /shared directory.

- Clone New Relic Report Repository

```shell
git clone https://github.com/newrelic/nr-reports.git
```

- Create a configuration file in  include/manifest.json

```json
"reports": [
    {
      "id": "monthly-report-infrastructure-csv",
      "name": "Monthy Report Infrastructure Application Export",
      "query": "FROM SystemSample SELECT average(cpuPercent), average(memoryUsedPercent), average(diskUsedPercent)  FACET CONCAT(yearOf(timestamp),'-', monthOf(timestamp, numeric), '-', dayOfMonthOf(timestamp) ),  hostname SINCE 30 days ago ",
      "accountIds": [412XXXX],
      "publishConfigs": [
        {
          "id": "email-report-to-team-lead",
          "name": "Email Monthy Report Infrastructure Application Export",
          "enabled": true,
          "channels": [
            {
              "id": "send-email",
              "name": "Email CSV report to leadership",
              "type": "email",
              "subject": "Monthy CSV Reports",
              "from": "noreply@numbers.local",
              "to": "sre@local.number"            
            }
          ]
        },
        {
          "id": "copy-file-to-share-folder",
          "name": "Copy file to shared folder",
        "enabled": true,
          "file": "file",
          "destDir": "../shared"
        }
      ]
    }
  ]
```

- Provide New Relic User Key

```shell
export NEWRELIC_API_KEY=NRAK-XXXXCWWVDELIESQ5HOXXXXXXXX  Running Report using CLI to send it via email  
```

- Running Report using CLI to export to file
  

```csv
2025-3-7,ip-172-55-0-18.us-west-1.compute.internal,96.60909271541009,48.125390290364535,46.09558587597476
2025-2-24,ip-172-55-0-230.us-west-1.compute.internal,80.56907379745788,72.22668904493572,63.02241926143477
2025-3-5,ip-172-55-1-30.us-west-1.compute.internal,80.00059415402947,70.45140724196332,44.44316987752953
2025-2-25,ip-172-55-1-30.us-west-1.compute.internal,79.24491489267055,69.46324664053066,51.986003841133524
2025-2-24,ip-172-55-1-30.us-west-1.compute.internal,79.11447436629201,69.6598443623585,50.00225214805742
2025-2-23,ip-172-55-1-30.us-west-1.compute.internal,78.96558749066773,69.69816959642057,47.56364219981973
2025-2-22,ip-172-55-1-30.us-west-1.compute.internal,77.95783378986545,69.55012400593432,45.60866208243937
2025-3-17,ip-172-55-0-162.us-west-1.compute.internal,77.95216780161854,65.42834469450302,56.06728147396647
2025-2-27,ip-172-55-1-30.us-west-1.compute.internal,77.88994464152246,67.71309150787259,37.95243397356807
2025-2-28,ip-172-55-1-30.us-west-1.compute.internal,77.29462638314907,67.79869230187556,39.30579816256979
```

5. Running Report using CLI to send it via email
  

```shell
sh nr-reports-cli/bin/nr-reports.sh -f include/manifest.json -u email-report-to-team-lead
```

Sample Output ![CSV Email Output]({{ site.baseurl }}/assets/images/nr-report-csv.jpg)

