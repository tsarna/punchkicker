#!/bin/sh
echo
echo "#####################################################################"
echo -n "Beginning Punch Kicker initialization at " && date
echo "#####################################################################"

export CLOUD_LIB="/var/lib/cloud"
export CLOUD_VAR="/var/lib/cloud"
export KICK_TMP=${KICK_TMP:-/tmp/punchkicker}
export KICK_VENV=${KICK_VENV:-${KICK_TMP}/venv}
export KICK_DIR=${KICK_DIR:-/run/punchkicker}
export KICK_D=${KICK_D:-${KICK_DIR}/kick.d}
export KICK_FILES_DIR=${KICK_FILES_DIR:-${KICK_DIR}/files}

export PYTHONPATH=${KICK_DIR}/python

if ! mountpoint -q /tmp; then
    mount -t tmpfs tmpfs /tmp
fi

echo && echo "Installing py3-virtualenv"
apk add py3-virtualenv

echo
mkdir -p ${KICK_TMP}
virtualenv ${KICK_VENV}
export PATH=${KICK_VENV}/bin:$PATH

echo && echo "Installing requests module:"
pip3 install requests # must be preinstalled for punchkicker module

cd ${KICK_D} && \
for script in *; do
    # Skip directories and any lock files
    [[ -f "$script" && "$script" != *.lock~ ]] || continue

    echo; echo "### $script:"
    ${KICK_D}/$script
    ec=$?
    if [ "$ec" != "0" ]; then
        echo
        echo "****** $script Failed with exit code $ec"
        exit $ec
    fi
done
