#!/bin/sh

set -x

DS="HumanEval"

rm -f $DS/Testing_${DS}/mutant_type.csv
#rm -f $DS/Testing_${DS}/*/Mutants/*
for SHOTS in normal fewshot; do
    rm -f $DS/Testing_${DS}/${SHOTS}_synfix.csv
    rm -f $DS/Testing_${DS}/${SHOTS}_semfix.csv
    rm -f $DS/Testing_${DS}/${SHOTS}_mutant_score.csv
    rm -f $DS/Testing_${DS}/${SHOTS}_gpt4o_completions.jsonl
    rm -rf $DS/Testing_${DS}/*/gpt4o
done

for SAMPLE in {0..163}; do
    echo ">>>>> generating $SAMPLE"
    python3 MuTAP/Mutants_generation.py $DS $SAMPLE script_ mutant_type.csv
done

for SHOTS in normal fewshot; do
    START_TIME=$(date +%s)
    echo ">>>>> $SHOTS starting at $START_TIME ($(date -d @${START_TIME}))"

    rm -f gpt4o_completions.jsonl

    for SAMPLE in {0..163}; do
        echo ">>>>> running $SAMPLE $SHOTS"
        python3 MuTAP/generate_test_oracle.py $SHOTS $DS $SAMPLE script_NDS_ "${SHOTS}_synfixed_" "${SHOTS}_synfix.csv"
        python3 MuTAP/semantic_error_correction.py $DS $SAMPLE "${SHOTS}_synfixed_" "${SHOTS}_semfixed_" "${SHOTS}_semfix.csv"
        python3 MuTAP/Mutation_Score.py $DS $SAMPLE "${SHOTS}_semfixed_" "${SHOTS}_mutant_score.csv"
        python3 MuTAP/augmented_prompt.py $SHOTS $DS $SAMPLE "${SHOTS}_semfixed_" "${SHOTS}_mut_" "${SHOTS}_mutant_score.csv"
        python3 MuTAP/Merge_all_mut.py $DS $SAMPLE "${SHOTS}_semfixed_" "${SHOTS}_mut_" "${SHOTS}_full_"
    done

    mv gpt4o_completions.jsonl $DS/Testing_${DS}/${SHOTS}_gpt4o_completions.jsonl

    END_TIME=$(date +%s)
    ELAPSED_TIME=$((END_TIME - START_TIME))
    echo ">>>>> $SHOTS done at $END_TIME ($(date -d @${END_TIME})); took ${ELAPSED_TIME} s"
done
