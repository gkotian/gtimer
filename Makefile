# ---- Variables ---------------------------------------------------------------

MAKEFILE_DIR := $(patsubst %/,%,$(dir $(realpath $(firstword $(MAKEFILE_LIST)))))
PARENT_DIR   := $(patsubst %/,%,$(dir $(MAKEFILE_DIR)))
PROJECT_NAME := $(notdir $(MAKEFILE_DIR))

REMOTE_USER := gautam
REMOTE_HOST := 192.168.0.29

ARCHIVE := /tmp/$(PROJECT_NAME).tar.xz

TAR_EXCLUDES := \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='tags'


# ---- Targets -----------------------------------------------------------------

## Deploys the application
deploy:
	@tar $(TAR_EXCLUDES) -cJf $(ARCHIVE) -C $(PARENT_DIR) $(PROJECT_NAME)
	@rsync -av $(ARCHIVE) $(REMOTE_USER)@$(REMOTE_HOST):$(ARCHIVE)
	@rm -f $(ARCHIVE)
	@ssh $(REMOTE_USER)@$(REMOTE_HOST) '\
	  rm -rf $(MAKEFILE_DIR).old && \
	  if [ -d $(MAKEFILE_DIR) ]; then mv $(MAKEFILE_DIR) $(MAKEFILE_DIR).old; fi && \
	  mkdir -p $(PARENT_DIR) && \
	  tar -xJf $(ARCHIVE) -C $(PARENT_DIR)'

.PHONY: deploy


# ---- Included files ----------------------------------------------------------

# Include 'extras.Makefile' to get additional convenience variables & targets.
# (The include statement is intentionally prefixed with a '-' so it doesn't
# throw an error if 'extras.Makefile' doesn't exist.)
-include ${HOME}/.config/gkotian/extras.Makefile
