.PHONY: pipeline-init verify

pipeline-init:
	bash scripts/init_pipeline.sh

verify:
	bash scripts/verify.sh
