to get started:
- ensure docker is running (sudo systemctl status docker shows “active”)
- make sure you've enough disk space for the image 

note: the tutorial is a bit outdated. to build the docker image it's not 
python -m swesmith.build_repo.create_images --repos Instagram/MonkeyType

python -m swesmith.build_repo.create_images --profiles Instagram/MonkeyType

build tutorial docker with: python -m swesmith.build_repo.create_images \
  -p jyangballin/swesmith.x86_64.instagram_1776_monkeytype.70c3acf6 \
  -y


then test the docker image works as expected with:
docker run -it --rm jyangballin/swesmith.x86_64.instagram_1776_monkeytype.70c3acf6

to generate lm modify candidates:
python -m swesmith.bug_gen.llm.modify   Instagram__MonkeyType.70c3acf6   --n_bugs 1   --model anthropic/claude-3-haiku-20240307   --config_file configs/bug_gen/lm_modify.yml
(after setting ANTHROPIC_API_KEY)


unit tests:
SWE-smith/tests/profiles/test_base.py -> test_extract_files

created FileEntity class 


example command:
python -m swesmith.bug_gen.augment.add_feature   Instagram__MonkeyType.70c3acf6   --n_bugs 1   --model anthropic/claude-3-haiku-20240307   --config_file configs/bug_gen/lm_augment.yml

