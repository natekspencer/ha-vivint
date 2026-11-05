#!/bin/bash

YEAR=$(date +"%Y")

# Attach a backup suffix to -i so this works with both GNU and BSD (macOS) sed
sed -E -i.bak "s/(Copyright( \(c\)| ©)? [0-9]{4})(–[0-9]{4})?/\1–$YEAR/" LICENSE
status=$?
rm -f LICENSE.bak
exit $status
