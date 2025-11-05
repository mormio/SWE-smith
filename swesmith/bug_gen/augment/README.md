# SWE-smith new methodology
SWE-smith introduces bugs into repositories by prompting LLMs to rewrite or modify existing functions or classes with the goal of inserting faults.  
I identify two key limitations that my implementation aims to address:
 1. In real-world software, bugs more commonly arise as a byproduct of implementing _new functionality_ rather than from intentionally introducing errors.
 2. These methods limit bugs to a single function or class, even though a single bug might span a larger space, such as an entire file or module.

Therefore, my suggested methodology prompts LLMs instead to augment the existing code in some way, with the goal of enhancing its functionality. The hope is to emulate the real code-generating process which tends to create bugs in codebases. The approach allows configurable granularity: changes can target a single function/class or span an entire file (see `scope` flag).

**New code is predominantly in /swesmith/bug_gen/augment/add_feature.py**

# Running the code

This method was tested on two repositories: `Instagram/MonkeyType` (as used in the tutorial) and `pydantic/pydantic`. Pick one and follow the instructions. 

1. Start by ensuring docker is running and that you have enough disk space for the images. In the root `.env` file put your `ANTHROPIC_API_KEY`.
2. Create the conda env for the target repo (run this from the SWE-smith root)
		 - Instagram: `python -m swesmith.build_repo.try_install_py Instagram/MonkeyType configs/install_repo.sh --commit 70c3acf62950be5dfb28743c7a719bfdecebcd84`
		 - Pydantic: `python -m swesmith.build_repo.try_install_py pydantic/pydantic configs/install_repo.sh --commit acb0f10fda1c78441e052c57b4288bc91431f852`
3. Build the docker images
		 - Instagram: `python -m swesmith.build_repo.create_images -p jyangballin/swesmith.x86_64.instagram_1776_monkeytype.70c3acf6 -y`
		 - Pydantic: `python -m swesmith.build_repo.create_images -p jyangballin/swesmith.x86_64.pydantic_1776_pydantic.acb0f10f -y`
4. Going forward, replace `<repo>` with either `Instagram__MonkeyType.70c3acf6` or `pydantic__pydantic.acb0f10f`
5. Example command to **generate instances**: `python -m swesmith.bug_gen.augment.add_feature <repo> --n_bugs 1 --max_bugs 8 --model anthropic/claude-3-haiku-20240307 --config_file configs/bug_gen/lm_augment.yml`
		 - By default the `scope` is set to `entity`. Optionally pass `--scope file` with the above command. 
6. Collect candidate tasks for validation: `python -m swesmith.bug_gen.collect_patches logs/augment_bug_gen/<repo>`
7. Validate: `python -m swesmith.harness.valid logs/augment_bug_gen/<repo>_all_patches.json`
8. Evaluate: No task instances passed validation (0 F2P), therefore evaluation was not run.

# Generated instances

8 instances were created for each repository. They were created using the --scope entity flag, but you may test the code with the --scope file flag. 
`/swesmith/bug_gen/augment/logs/augment_bug_gen`

# Validation results

To contextualize performance, I re-ran the SWE-Bench LM-modify baseline under identical conditions (same repo, environment, and validation procedure).  
The baseline likewise failed to produce any validated bugs, suggesting that the limitation is environmental (e.g., repository complexity, small sample size) rather than methodological.

| Repo | Augment (my method) | LM modify (swe-bench) |
|------|---------------------|------------------------|
|  Pydantic    | fail=0, timeout=8, 0_f2p=0, 1+_f2p=0 | fail=0, timeout=4, 0_f2p=4, 1+_f2p=0 |
|    Instagram  |fail=0, timeout=0, 0_f2p=8, 1+_f2p=0 |fail=0, timeout=0, 0_f2p=8, 1+_f2p=0|



## Evaluation

As mentioned above, since none of the generation runs yielded any f2p bugs, there was no evaluation run. 

## Implementation info

The config file containing system and user prompts can be found in `configs/bug_gen/lm_augment.yml`. 

The unit tests for my code were added _in situ_ rather than in this directory. 
	- `/swesmith/tests/profiles/test_base.py` -> test_extract_files() 
	- `/swesmith/tests/bug_gen/llm/test_gen_augmented.py` -> test_gen_augmented_returns_bugs()
