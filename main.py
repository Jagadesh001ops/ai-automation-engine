from dotenv import load_dotenv
load_dotenv()

from engine.intent_parser import parse_intent

request = """I have a research paper PDF.
I want to summarize it, extract the key concepts,
and generate 5 quiz questions for studying."""

plan = parse_intent(request)

print(f"Goal: {plan.goal}")
print(f"Total steps: {plan.estimated_steps}\n")
for i, step in enumerate(plan.steps, 1):
    print(f"Step {i}: {step.name}")
    print(f"  What: {step.description}")
    print(f"  Reads: {step.input_key} → Writes: {step.output_key}")