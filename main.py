from dotenv import load_dotenv
load_dotenv()

from engine.intent_parser import parse_intent
from engine.execution_engine import ExecutionEngine
from engine.llm_nodes import build_node_for_step

# ─── Sample document ──────────────────────────────────────────────────────────

SAMPLE_DOCUMENT = """
Artificial intelligence (AI) is transforming modern healthcare in profound ways.
Machine learning algorithms can now detect certain cancers from medical imaging
with accuracy comparable to experienced radiologists. Natural language processing
systems parse millions of clinical notes to identify patterns humans would miss.
Predictive models flag patients at risk of deterioration hours before traditional
warning signs appear.

However, significant challenges remain. AI systems trained on data from one
hospital often perform poorly at another due to differences in patient populations
and data collection practices. Bias in training data can lead to disparate
outcomes across demographic groups. Regulatory frameworks struggle to keep pace
with rapid technological advancement. Clinicians report alert fatigue from
systems that generate too many false positives.

Despite these hurdles, investment in healthcare AI continues to grow. Major
technology companies and startups alike are racing to build tools that promise
to reduce costs, improve outcomes, and address physician burnout. The coming
decade will likely determine whether AI becomes a transformative force in
medicine or remains a promising but underutilised technology.
"""

# ─── User request ─────────────────────────────────────────────────────────────

USER_REQUEST = """
I have a document about AI in healthcare.
Summarize it, extract the key concepts,
and generate quiz questions for studying.
"""

# ─── Step 1: Parse intent → get workflow plan ─────────────────────────────────

print("=" * 60)
print("STEP 1: Parsing intent...")
print("=" * 60)

plan = parse_intent(USER_REQUEST)

print(f"Goal    : {plan.goal}")
print(f"Steps   : {plan.estimated_steps}\n")
for i, step in enumerate(plan.steps, 1):
    print(f"  {i}. {step.name}")
    print(f"     {step.description}")
    print(f"     {step.input_key} → {step.output_key}")

# ─── Step 2: Build nodes from plan ───────────────────────────────────────────

print("\n" + "=" * 60)
print("STEP 2: Building nodes...")
print("=" * 60)

engine = ExecutionEngine()

for step in plan.steps:
    node = build_node_for_step(
        name=step.name,
        description=step.description,
        input_key=step.input_key,
        output_key=step.output_key
    )
    engine.register_node(step.name, node)
    print(f"  Registered: {step.name} → {type(node).__name__}")

# ─── Step 3: Run the pipeline ─────────────────────────────────────────────────

print("\n" + "=" * 60)
print("STEP 3: Running pipeline...")
print("=" * 60)

initial_state = {"document": SAMPLE_DOCUMENT}
final_state = engine.run(plan, initial_state)

# ─── Step 4: Print final output ───────────────────────────────────────────────

print("\n" + "=" * 60)
print("FINAL OUTPUT")
print("=" * 60)

output_keys = ["summary", "key_concepts", "quiz_questions"]

for key in output_keys:
    if key in final_state:
        print(f"\n── {key.upper().replace('_', ' ')} ──")
        print(final_state[key])