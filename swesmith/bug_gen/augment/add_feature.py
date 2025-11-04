"""
Purpose: Given a repository, generate patches for new features in the repository.

Usage: python -m swesmith.bug_gen.augment.add_feature \
    --n_bugs <n_bugs> \
    --config_file <config_file> \
    --model <model> \
    repo  # e.g., tkrajina__gpxpy.09fc46b3

Where model follows the litellm format.

Example:

python -m swesmith.bug_gen.augment.add_feature tkrajina__gpxpy.09fc46b3 --config_file configs/bug_gen/class_basic.yml --model claude-3-7-sonnet-20250219 --n_bugs 1
"""

import logging 
import argparse
import litellm
import yaml 
from tqdm.auto import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm
from typing import Any
import shutil 
from concurrent.futures import ThreadPoolExecutor, as_completed
import os 
import jinja2
import random
import dataclasses
import json
from litellm import completion
from litellm.cost_calculator import completion_cost

from swesmith.bug_gen.llm.utils import extract_code_block
from dotenv import load_dotenv
from swesmith.profiles import registry
from swesmith.constants import (
    LOG_DIR_AUGMENT,
    PREFIX_METADATA, 
    PREFIX_BUG,
    FileEntity,
    CodeEntity,
    BugRewrite
)
from swesmith.bug_gen.utils import (
    apply_code_change,
    get_bug_directory,
    get_patch,
    apply_file_change,
)

load_dotenv()
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
litellm.drop_params = True
litellm.suppress_debug_info = True
random.seed(24)


def gen_augmented_entity(
    candidate: CodeEntity, configs: dict, n_bugs: int, model: str, temperature: float = 1
) -> list[BugRewrite]:
    PROMPT_KEYS = ["system", "entity_instance"]
    """
    Given the source code of a function, return n feature-augmented (buggy) versions.
    """

    def format_prompt(prompt: str | None, config: dict, candidate: CodeEntity) -> str:
        if not prompt:
            return ""
        env = jinja2.Environment()

        def jinja_shuffle(seq):
            result = list(seq)
            random.shuffle(result)
            return result

        env.filters["shuffle"] = jinja_shuffle
        template = env.from_string(prompt)

        candidate_dict = {
            field.name: getattr(candidate, field.name)
            for field in dataclasses.fields(candidate)
        }
        return template.render(**candidate_dict, **config.get("parameters", {}))
    
    def get_role(key: str) -> str:
        if key == "system":
            return "system"
        return "user"

    # Get prompt content
    prompt_content = {
        "func_name": candidate.name,
        "file_src_code": open(candidate.file_path).read(),
    }

    # Generate a rewrite
    messages = [
        {
            "content": configs[k].format(**prompt_content),
            "role": "user" if k != "system" else "system",
        }
        for k in PROMPT_KEYS
        if k in configs
    ]
    # Remove empty messages
    messages = [x for x in messages if x["content"]]
    bugs = []
    response: Any = completion(model=model, messages=messages, n=n_bugs, temperature=temperature)
    for choice in response.choices:
        message = choice.message
        explanation = (
            message.content.split("Explanation:")[-1].strip()
            if "Explanation" in message.content
            else message.content.split("```")[-1].strip()   
        )
        bugs.append(
            BugRewrite(
                rewrite=extract_code_block(message.content),
                explanation=explanation,
                cost=completion_cost(completion_response=response) / n_bugs, #TODO: the n_bugs param is confusing. 
                output=message.content,
                strategy="llm_augmented_entity",
            )
        )
    return bugs


def gen_augmented_file(
    candidate: FileEntity, configs: dict, n_bugs: int, model: str, temperature: float = 1
) -> list[BugRewrite]:
    PROMPT_KEYS = ["system", "file_instance"]
    """
    Given the source code of a file, return n feature-augmented (buggy) versions.
    """

    def format_prompt(prompt: str | None, config: dict, candidate: CodeEntity) -> str:
        if not prompt:
            return ""
        env = jinja2.Environment()

        def jinja_shuffle(seq):
            result = list(seq)
            random.shuffle(result)
            return result

        env.filters["shuffle"] = jinja_shuffle
        template = env.from_string(prompt)

        candidate_dict = {
            field.name: getattr(candidate, field.name)
            for field in dataclasses.fields(candidate)
        }
        return template.render(**candidate_dict, **config.get("parameters", {}))
    
    def get_role(key: str) -> str:
        if key == "system":
            return "system"
        return "user"

    # Get prompt content
    prompt_content = {
        "file_path": candidate.file_path,
        "file_src_code": open(candidate.file_path).read(),
    }

    # Generate a rewrite
    messages = [
        {
            "content": configs[k].format(**prompt_content),
            "role": "user" if k != "system" else "system",
        }
        for k in PROMPT_KEYS
        if k in configs
    ]
    # Remove empty messages
    messages = [x for x in messages if x["content"]]
    bugs = []
    response: Any = completion(model=model, messages=messages, n=n_bugs, temperature=temperature)
    for choice in response.choices:
        message = choice.message
        explanation = (
            message.content.split("Explanation:")[-1].strip()
            if "Explanation" in message.content
            else message.content.split("```")[-1].strip()
        )
        bugs.append(
            BugRewrite(
                rewrite=extract_code_block(message.content),
                explanation=explanation,
                cost=completion_cost(completion_response=response) / n_bugs, #TODO: the n_bugs param is confusing. 
                output=message.content,
                strategy="llm_augmented_file",
            )
        )
    return bugs



def main(
    config_file: str,
    model: str,
    n_bugs: int,
    repo: str,
    scope: str = "entity",
    n_workers: int = 1,
    max_bugs: int = -1,
    temperature: float = 1.4,
):
    # Check arguments
    assert os.path.exists(config_file), f"{config_file} not found"
    assert n_bugs > 0, "n_bugs must be greater than 0"
    configs = yaml.safe_load(open(config_file))
    # assert all(key in configs for key in PROMPT_KEYS + ["name"]), (
    #     f"Missing keys in {config_file}"
    # ) #TODO: fix this. prompt keys different according to scope 

    # Clone repository, identify valid candidates
    print("Cloning repository...")
    rp = registry.get(repo)
    rp.clone()
    print("Extracting candidates...")
    if scope == "entity":
        candidates = rp.extract_entities()
    elif scope == "file":
        candidates = rp.extract_files()
    print(f"{len(candidates)} candidates found in {repo}")
    if not candidates:
        print(f"No candidates found in {repo}.")
        return

    # Adjust candidates if max_bugs is specified
    if max_bugs > 0:
        max_candidates = max_bugs // n_bugs
        if max_candidates < len(candidates):
            candidates = candidates[:max_candidates]
            print(
                f"Limited to {len(candidates)} candidates to generate ~{len(candidates) * n_bugs} bugs (max: {max_bugs})"
            )
        else:
            print(f"Will generate {len(candidates) * n_bugs} bugs (max: {max_bugs})")

    print(f"Generating bugs in {repo} using {model}...")

     # Set up logging
    log_dir = LOG_DIR_AUGMENT / repo
    log_dir.mkdir(parents=True, exist_ok=True)
    print(f"Logging bugs to {log_dir}")

    def _process_candidate(candidate: CodeEntity | FileEntity):
        # Run bug generation
        if isinstance(candidate, CodeEntity):
            assert scope == "entity"
            bugs = gen_augmented_entity(candidate, configs, n_bugs, model, temperature)
        elif isinstance(candidate, FileEntity):
            assert scope == "file"
            bugs = gen_augmented_file(candidate, configs, n_bugs, model, temperature)
        else:
            raise ValueError(f"Invalid candidate type: {type(candidate)}")
        
        cost, n_bugs_generated, n_generation_failed = sum([x.cost for x in bugs]), 0, 0

        for bug in bugs:
            # Create artifacts
            bug_dir = get_bug_directory(log_dir, candidate)
            bug_dir.mkdir(parents=True, exist_ok=True)
            uuid_str = f"{configs['name']}__{bug.get_hash()}"
            metadata_path = f"{PREFIX_METADATA}__{uuid_str}.json"
            bug_path = f"{PREFIX_BUG}__{uuid_str}.diff"

            try:
                with open(bug_dir / metadata_path, "w") as f:
                    json.dump(bug.to_dict(), f, indent=2)
                if scope == "entity":
                    apply_code_change(candidate, bug)
                elif scope == "file":
                    apply_file_change(candidate, bug)
                patch = get_patch(repo, reset_changes=True)
                if not patch:
                    raise ValueError("Patch is empty.")
                with open(bug_dir / bug_path, "w") as f:
                    f.write(patch)
            except Exception as e:
                print(
                    f"Error applying bug to {candidate.name} in {candidate.file_path}: {e}" if scope == "entity" else f"Error applying bug to {candidate.file_path}: {e}",
                )
                # import traceback
                # print(f"Traceback:\n{''.join(traceback.format_exc())}")
                (bug_dir / metadata_path).unlink(missing_ok=True)
                n_generation_failed += 1
                continue
            else:
                n_bugs_generated += 1
        return {
            "cost": cost,
            "n_bugs_generated": n_bugs_generated,
            "n_generation_failed": n_generation_failed,
        }

    stats = {"cost": 0.0, "n_bugs_generated": 0, "n_generation_failed": 0}
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = [
            executor.submit(_process_candidate, candidate) for candidate in candidates
        ]

        with logging_redirect_tqdm():
            with tqdm(total=len(candidates), desc="Candidates") as pbar:
                for future in as_completed(futures):
                    cost = future.result()
                    for k, v in cost.items():
                        stats[k] += v
                    pbar.set_postfix(stats, refresh=True)
                    pbar.update(1)

    shutil.rmtree(repo)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "repo",
        type=str,
        help="Name of a SWE-smith repository to generate bugs for.",
    )
    parser.add_argument(
        "-c",
        "--config_file",
        type=str,
        help="Configuration file containing bug gen. strategy prompts",
        required=True,
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Model to use for bug generation",
        default="openai/gpt-4o",
    )
    parser.add_argument(
        "-n",
        "--n_bugs",
        type=int,
        help="Number of bugs to generate per entity",
        default=1,
    )
    parser.add_argument(
        "-m",
        "--max_bugs",
        type=int,
        help="Total, maximum number of bugs to generate",
        default=-1,
    )
    parser.add_argument(
        "-w", "--n_workers", type=int, help="Number of workers to use", default=1
    )
    parser.add_argument(
        "--temperature",
        type=float,
        help="Temperature for the model",
        default=1,
    )
    parser.add_argument(
        "--scope",
        type=str,
        help="Scope of the bug generation",
        default="entity",
    )
    args = parser.parse_args()
    main(**vars(args))
