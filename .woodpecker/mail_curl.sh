#!/bin/sh

_reports_file="${MAIL_HOST}"

_subject="$CI_REPO_NAME | pipeline $CI_PIPELINE_STATUS for $CI_COMMIT_BRANCH | $CI_COMMIT_MESSAGE"

if [ "${CI_PIPELINE_STATUS}" = 'success' ]; then
    _message="Pipeline was successful and #$CI_PIPELINE_NUMBER has passed."
else
    _message="Pipeline #$CI_PIPELINE_NUMBER has failed!"
fi

echo "From: $MAIL_FROM" >> $MAIL_HOST
echo "To: $MAIL_FROM" >> $MAIL_HOST
echo "Subject: $_subject" >> $MAIL_HOST
echo "" >> $MAIL_HOST
echo "$_message" >> $MAIL_HOST
echo "" >> $MAIL_HOST
echo "Project: $CI_REPO_NAME ( $CI_REPO_LINK )" >> $MAIL_HOST
echo "Branch: $CI_COMMIT_BRANCH ( $CI_REPO_LINK/src/branch/$CI_COMMIT_BRANCH )" >> $MAIL_HOST
echo "" >> $MAIL_HOST
echo "Commit: $CI_COMMIT_LINK" >> $MAIL_HOST
echo "Commit Message: $CI_COMMIT_MESSAGE" >> $MAIL_HOST
echo "" >> $MAIL_HOST
echo "Pipeline: $CI_PIPELINE_NUMBER ( https://$CI_SYSTEM_HOST/$CI_REPO/pipeline/$CI_PIPELINE_NUMBER ) triggered by $CI_COMMIT_AUTHOR" >> $MAIL_HOST
echo "" >> $MAIL_HOST

if [ ! -f "${_reports_file}" ]; then
	echo "File '${_reports_file}' could not be found! No message will be sent."
	exit 0;
else
    echo "Contents of ${_reports_file}:"
    command cat ${_reports_file}
fi

command curl --url "smtp://$MAIL_HOST:587" --mail-from "$MAIL_FROM" --mail-rcpt "$MAIL_RECIPIENTS" --upload-file "$MAIL_HOST" --user "$MAIL_USER:$MAIL_PASS" --ssl-reqd
