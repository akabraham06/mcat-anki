# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""MCAT starter content: tagged learning cards and auto-graded exam questions.

Tags follow ``mcat::<section>::<topic>`` so the Rust engine can map every card
onto the embedded taxonomy for coverage and scoring.

Content comes in three flavours:

* ``KNOWLEDGE`` — plain recall (Basic notetype). Feeds the *memory* model.
* ``LEARNING_TYPED`` — typed fill-in recall (native ``{{type:Answer}}``).
  Also memory-model learning cards, but graded against an exact typed answer.
* ``EXAM_MCQ`` — multiple-choice, auto-graded exam questions (MCATExam
  notetype). Feeds the *performance* model. Each item probes the same idea as a
  KNOWLEDGE card in an application form, which is what the transfer-gap metric
  measures (recall vs. application).
* ``CARS_PASSAGES`` — original reading passages, each with several MCQs across
  all four CARS skills (MCATCarsPassage notetype). Also performance-model cards.

Every exam item carries exactly one ``mcat::<section>::<topic>`` tag plus the
``mcat::exam`` marker tag, so the engine attributes each graded review to a
single topic (no double counting) and recognises it as a performance card.
"""

# (tag, front, back) rendered with the Basic notetype -> memory model.
KNOWLEDGE: list[tuple[str, str, str]] = [
    # --- Chem/Phys ---
    ("mcat::chemphys::thermodynamics",
     "State the first law of thermodynamics.",
     "\u0394U = q + w; internal energy change equals heat added plus work done on the system."),
    ("mcat::chemphys::thermodynamics",
     "What is the sign of \u0394G for a spontaneous process?",
     "Negative (\u0394G < 0)."),
    ("mcat::chemphys::kinetics",
     "How does a catalyst affect a reaction?",
     "Lowers activation energy, increasing rate; does not change \u0394G or equilibrium."),
    ("mcat::chemphys::kinetics",
     "Define the rate-determining step.",
     "The slowest elementary step; it limits the overall reaction rate."),
    ("mcat::chemphys::acids_bases",
     "Define a Bronsted-Lowry acid.",
     "A proton (H+) donor."),
    ("mcat::chemphys::acids_bases",
     "What is the pH at the equivalence point of a strong acid + strong base titration?",
     "7 (neutral)."),
    ("mcat::chemphys::atomic_structure",
     "State Hund's rule.",
     "Electrons fill degenerate orbitals singly, with parallel spins, before pairing."),
    ("mcat::chemphys::electrochemistry",
     "In a galvanic cell, oxidation occurs at which electrode?",
     "The anode."),
    ("mcat::chemphys::electrochemistry",
     "What does a positive cell potential (E\u00b0cell) indicate?",
     "A spontaneous redox reaction (\u0394G < 0)."),
    ("mcat::chemphys::fluids",
     "State Bernoulli's principle qualitatively.",
     "Faster-moving fluid exerts lower pressure; total mechanical energy per volume is conserved."),
    # --- Bio/Biochem ---
    ("mcat::biobiochem::amino_acids",
     "Which amino acid is achiral?",
     "Glycine (its side chain is a hydrogen)."),
    ("mcat::biobiochem::amino_acids",
     "Name the two acidic (negatively charged) amino acids.",
     "Aspartate and glutamate."),
    ("mcat::biobiochem::protein_structure",
     "What bonds stabilize a protein's secondary structure?",
     "Hydrogen bonds between backbone amide and carbonyl groups."),
    ("mcat::biobiochem::protein_structure",
     "What covalent bond stabilizes tertiary/quaternary structure between cysteines?",
     "Disulfide bonds."),
    ("mcat::biobiochem::enzymes",
     "What does a competitive inhibitor do to Km and Vmax?",
     "Increases apparent Km; Vmax unchanged."),
    ("mcat::biobiochem::enzymes",
     "What does a noncompetitive inhibitor do to Km and Vmax?",
     "Km unchanged; Vmax decreased."),
    ("mcat::biobiochem::metabolism",
     "Where does the citric acid (Krebs) cycle occur?",
     "The mitochondrial matrix."),
    ("mcat::biobiochem::metabolism",
     "What is the net ATP yield from one glucose via aerobic respiration (typical estimate)?",
     "About 30-32 ATP."),
    ("mcat::biobiochem::glycolysis",
     "What is the net ATP and NADH yield of glycolysis per glucose?",
     "Net 2 ATP and 2 NADH."),
    ("mcat::biobiochem::glycolysis",
     "What is the committed (rate-limiting) step of glycolysis?",
     "Phosphofructokinase-1 (PFK-1) converting F6P to F1,6BP."),
    ("mcat::biobiochem::molecular_genetics",
     "In which direction does DNA polymerase synthesize?",
     "5' to 3'."),
    ("mcat::biobiochem::membranes",
     "What kind of transport moves solutes against their gradient using ATP?",
     "Primary active transport."),
    # --- Psych/Soc ---
    ("mcat::psychsoc::learning_memory",
     "Distinguish classical from operant conditioning.",
     "Classical: association between stimuli. Operant: behavior shaped by consequences (reinforcement/punishment)."),
    ("mcat::psychsoc::learning_memory",
     "What is the spacing effect?",
     "Distributed practice over time yields better retention than massed practice (cramming)."),
    ("mcat::psychsoc::sensation_perception",
     "Define the absolute threshold.",
     "The minimum stimulus intensity detectable 50% of the time."),
    ("mcat::psychsoc::sensation_perception",
     "State Weber's law.",
     "The just-noticeable difference is a constant proportion of the original stimulus."),
    ("mcat::psychsoc::cognition",
     "What is functional fixedness?",
     "A cognitive bias limiting an object to its traditional use."),
    ("mcat::psychsoc::social_psychology",
     "Define the fundamental attribution error.",
     "Overattributing others' behavior to disposition and underweighting situation."),
    ("mcat::psychsoc::social_psychology",
     "What is the mere-exposure effect?",
     "Repeated exposure to a stimulus increases liking for it."),
    ("mcat::psychsoc::identity",
     "Distinguish an achieved from an ascribed status.",
     "Achieved: earned through effort/choice. Ascribed: assigned at birth or involuntarily."),
    ("mcat::psychsoc::demographics",
     "Define demographic transition.",
     "Shift from high birth/death rates to low birth/death rates as a society industrializes."),
]

# (tag, question, exact_answer) rendered with the MCATTypedLearning notetype,
# which uses Anki's native {{type:Answer}} to grade a short typed response.
# These are memory-model learning cards (no exam tag).
LEARNING_TYPED: list[tuple[str, str, str]] = [
    ("mcat::biobiochem::glycolysis",
     "Type the rate-limiting enzyme of glycolysis (its common abbreviation).",
     "PFK-1"),
    ("mcat::chemphys::acids_bases",
     "Type the pH at the equivalence point of a strong acid + strong base titration.",
     "7"),
    ("mcat::biobiochem::amino_acids",
     "Type the name of the only achiral (non-stereogenic) amino acid.",
     "glycine"),
    ("mcat::chemphys::electrochemistry",
     "In a galvanic cell, oxidation occurs at the ___ electrode. Type the electrode name.",
     "anode"),
    ("mcat::biobiochem::metabolism",
     "Type the organelle that houses the citric acid (Krebs) cycle.",
     "mitochondrion"),
    ("mcat::psychsoc::learning_memory",
     "Distributed practice beating cramming is called the ___ effect. Type the missing word.",
     "spacing"),
]

# (tag, question, [A, B, C, D], correct_letter, explanation) rendered with the
# MCATExam notetype -> performance model. Auto-graded: correct -> Good(3),
# wrong -> Again(1).
EXAM_MCQ: list[tuple[str, str, list[str], str, str]] = [
    # --- Chem/Phys: thermodynamics ---
    ("mcat::chemphys::thermodynamics",
     "A reaction has \u0394H > 0 and \u0394S > 0. At what temperatures is it spontaneous?",
     ["At all temperatures", "At high temperatures", "At low temperatures", "Never"],
     "B",
     "\u0394G = \u0394H \u2212 T\u0394S. With \u0394H > 0 and \u0394S > 0, high T makes the \u2212T\u0394S term dominate, so \u0394G < 0."),
    ("mcat::chemphys::thermodynamics",
     "For a reaction with \u0394S < 0, how does raising the temperature affect spontaneity?",
     ["Makes it more spontaneous", "Makes it less spontaneous", "No effect", "Always spontaneous"],
     "B",
     "With \u0394S < 0, the \u2212T\u0394S term is positive and grows with T, raising \u0394G."),
    ("mcat::chemphys::thermodynamics",
     "A process releases heat and increases order. Classify \u0394H and \u0394S.",
     ["\u0394H < 0, \u0394S < 0", "\u0394H > 0, \u0394S > 0", "\u0394H < 0, \u0394S > 0", "\u0394H > 0, \u0394S < 0"],
     "A",
     "Releasing heat is exothermic (\u0394H < 0); increased order means \u0394S < 0."),
    # --- Chem/Phys: kinetics ---
    ("mcat::chemphys::kinetics",
     "Adding a catalyst doubles the forward rate. What happens to Keq?",
     ["It doubles", "It halves", "It is unchanged", "It depends on temperature"],
     "C",
     "A catalyst speeds forward and reverse equally; Keq and \u0394G are unchanged."),
    ("mcat::chemphys::kinetics",
     "For A + B \u2192 C, doubling [A] quadruples the rate. What is the order in A?",
     ["Zero order", "First order", "Second order", "Third order"],
     "C",
     "rate \u221d [A]^n and 2^n = 4, so n = 2."),
    ("mcat::chemphys::kinetics",
     "A multi-step mechanism speeds up when its slowest step is bypassed. Why?",
     ["The fast steps set the rate", "The slowest step is rate-determining",
      "Catalysts remove all intermediates", "Equilibrium shifts right"],
     "B",
     "Overall rate is limited by the slowest (rate-determining) step."),
    # --- Chem/Phys: acids_bases ---
    ("mcat::chemphys::acids_bases",
     "What is the pH of 0.01 M HCl?",
     ["1", "2", "7", "12"],
     "B",
     "A strong acid fully dissociates; pH = \u2212log(0.01) = 2."),
    ("mcat::chemphys::acids_bases",
     "Titrating a weak acid with a strong base: the equivalence-point pH is?",
     ["Below 7", "Exactly 7", "Above 7", "Impossible to determine"],
     "C",
     "The conjugate base remaining at equivalence makes the solution basic."),
    ("mcat::chemphys::acids_bases",
     "Identify the conjugate base of H2PO4\u207b.",
     ["H3PO4", "HPO4\u00b2\u207b", "PO4\u00b3\u207b", "OH\u207b"],
     "B",
     "Removing one proton from H2PO4\u207b gives HPO4\u00b2\u207b."),
    # --- Chem/Phys: atomic_structure ---
    ("mcat::chemphys::atomic_structure",
     "How many unpaired electrons does nitrogen (2p\u00b3) have?",
     ["1", "2", "3", "0"],
     "C",
     "By Hund's rule the three 2p electrons occupy separate orbitals, all unpaired."),
    ("mcat::chemphys::atomic_structure",
     "Which has the larger radius, Na or Na\u207a?",
     ["Na", "Na\u207a", "They are equal", "It depends on temperature"],
     "A",
     "Losing an electron reduces electron-electron repulsion, so the cation is smaller."),
    # --- Chem/Phys: electrochemistry ---
    ("mcat::chemphys::electrochemistry",
     "In electrolysis, reduction occurs at which electrode?",
     ["The anode", "The cathode", "The salt bridge", "Both electrodes"],
     "B",
     "Reduction always occurs at the cathode, by definition."),
    ("mcat::chemphys::electrochemistry",
     "E\u00b0cell is negative. Is the reaction spontaneous as written?",
     ["Yes", "No", "Only at high temperature", "Only with a catalyst"],
     "B",
     "Negative E\u00b0 means \u0394G > 0, so the reaction is nonspontaneous as written."),
    ("mcat::chemphys::electrochemistry",
     "In a galvanic cell, electrons flow from which electrode to which?",
     ["Cathode to anode", "Anode to cathode", "In both directions", "They do not flow"],
     "B",
     "Electrons flow from the anode (oxidation) to the cathode (reduction)."),
    # --- Chem/Phys: fluids ---
    ("mcat::chemphys::fluids",
     "A fluid speeds up through a constriction. What happens to its pressure?",
     ["It increases", "It decreases", "It is unchanged", "It drops to zero"],
     "B",
     "By Bernoulli's principle, faster flow corresponds to lower pressure."),
    ("mcat::chemphys::fluids",
     "A pipe narrows to half its cross-sectional area. What happens to flow velocity?",
     ["It halves", "It is unchanged", "It doubles", "It quadruples"],
     "C",
     "Continuity (A1v1 = A2v2): halving the area doubles the velocity."),
    # --- Chem/Phys: stoichiometry ---
    ("mcat::chemphys::stoichiometry",
     "How many moles of O2 react with 2 mol H2 to form water?",
     ["0.5 mol", "1 mol", "2 mol", "4 mol"],
     "B",
     "2 H2 + O2 \u2192 2 H2O, so 2 mol H2 needs 1 mol O2."),
    ("mcat::chemphys::stoichiometry",
     "For N2 + 3 H2 \u2192 2 NH3 with 3 mol H2 and 1 mol N2, which is limiting?",
     ["H2", "N2", "Neither (exact ratio)", "NH3"],
     "C",
     "3 mol H2 to 1 mol N2 is exactly the 3:1 stoichiometric ratio, so neither is limiting."),
    # --- Chem/Phys: thermochemistry ---
    ("mcat::chemphys::thermochemistry",
     "Is bond breaking endothermic or exothermic?",
     ["Exothermic", "Endothermic", "Neither", "Always spontaneous"],
     "B",
     "Breaking a bond requires an input of energy, so it is endothermic."),
    ("mcat::chemphys::thermochemistry",
     "By Hess's law, if step 1 = \u2212100 kJ and step 2 = +40 kJ, the net \u0394H is?",
     ["\u2212140 kJ", "\u221260 kJ", "+60 kJ", "+140 kJ"],
     "B",
     "\u0394H is a state function; \u2212100 + 40 = \u221260 kJ."),
    # --- Bio/Biochem: amino_acids ---
    ("mcat::biobiochem::amino_acids",
     "At physiological pH, what is the charge on glutamate's side chain?",
     ["Positive", "Negative", "Neutral", "It has no side chain"],
     "B",
     "The side-chain carboxyl is deprotonated (carboxylate), giving a negative charge."),
    ("mcat::biobiochem::amino_acids",
     "Which amino acid disrupts alpha-helices because of its rigid ring?",
     ["Glycine", "Proline", "Alanine", "Serine"],
     "B",
     "Proline's ring locks its backbone and it lacks an amide H, breaking helices."),
    ("mcat::biobiochem::amino_acids",
     "A peptide residue has no stereocenter. Which amino acid is it?",
     ["Glycine", "Alanine", "Valine", "Cysteine"],
     "A",
     "Glycine's side chain is a hydrogen, so its alpha carbon is not a stereocenter."),
    # --- Bio/Biochem: protein_structure ---
    ("mcat::biobiochem::protein_structure",
     "A reducing agent breaks which protein bond?",
     ["Peptide bonds", "Hydrogen bonds", "Disulfide bonds", "Ionic bonds"],
     "C",
     "Reduction cleaves disulfide (S\u2013S) bonds back to free thiols."),
    ("mcat::biobiochem::protein_structure",
     "Beta-sheets are stabilized primarily by what interaction?",
     ["Disulfide bonds", "Backbone hydrogen bonds", "Hydrophobic packing only", "Peptide bonds"],
     "B",
     "Secondary structure, including beta-sheets, is held by backbone hydrogen bonds."),
    ("mcat::biobiochem::protein_structure",
     "Heat denaturation disrupts which level of structure first?",
     ["Primary", "Tertiary", "The peptide backbone", "Covalent bonds"],
     "B",
     "Non-covalent tertiary contacts unfold first; the primary sequence is retained."),
    # --- Bio/Biochem: enzymes ---
    ("mcat::biobiochem::enzymes",
     "A drug raises apparent Km but leaves Vmax unchanged. What kind of inhibitor is it?",
     ["Competitive", "Noncompetitive", "Uncompetitive", "Irreversible"],
     "A",
     "Competitive inhibitors raise apparent Km with Vmax unchanged (outcompeted by substrate)."),
    ("mcat::biobiochem::enzymes",
     "An inhibitor lowers Vmax but does not change Km. What type is it?",
     ["Competitive", "Noncompetitive", "None", "Allosteric activator"],
     "B",
     "Classic noncompetitive inhibition lowers Vmax while Km is unchanged."),
    ("mcat::biobiochem::enzymes",
     "Adding more substrate reverses the inhibition. Which inhibitor type is it?",
     ["Competitive", "Noncompetitive", "Uncompetitive", "Irreversible"],
     "A",
     "Competitive inhibition is overcome by increasing substrate concentration."),
    ("mcat::biobiochem::enzymes",
     "Enzyme activity rises then falls as temperature increases. The fall is caused by?",
     ["Lower substrate concentration", "Denaturation above the optimum",
      "A higher Km", "Product inhibition"],
     "B",
     "Above the optimal temperature the enzyme denatures, losing activity."),
    # --- Bio/Biochem: metabolism ---
    ("mcat::biobiochem::metabolism",
     "Which process occurs in the mitochondrial matrix?",
     ["Glycolysis", "The Krebs cycle", "Glycogenolysis", "Translation"],
     "B",
     "The citric acid (Krebs) cycle runs in the mitochondrial matrix; glycolysis is cytosolic."),
    ("mcat::biobiochem::metabolism",
     "Cyanide blocks complex IV. What happens to ATP synthesis?",
     ["It increases", "It halts", "It is unchanged", "It doubles"],
     "B",
     "Blocking the electron transport chain collapses the proton gradient, halting ATP synthesis."),
    ("mcat::biobiochem::metabolism",
     "Under anaerobic conditions in humans, what regenerates NAD\u207a?",
     ["The Krebs cycle", "Lactate fermentation", "Beta-oxidation", "The electron transport chain"],
     "B",
     "Lactate fermentation reoxidizes NADH to NAD\u207a so glycolysis can continue."),
    # --- Bio/Biochem: glycolysis ---
    ("mcat::biobiochem::glycolysis",
     "Glycolysis makes 4 ATP and invests 2. What is the net ATP?",
     ["2", "4", "6", "0"],
     "A",
     "Net ATP = 4 produced \u2212 2 invested = 2 per glucose."),
    ("mcat::biobiochem::glycolysis",
     "What is the main control enzyme of glycolysis?",
     ["Hexokinase", "PFK-1", "Pyruvate kinase", "Aldolase"],
     "B",
     "Phosphofructokinase-1 catalyzes the committed, rate-limiting step."),
    ("mcat::biobiochem::glycolysis",
     "High ATP inhibits PFK-1. What is this kind of regulation called?",
     ["Competitive inhibition", "Allosteric feedback inhibition",
      "Covalent modification", "Induced fit"],
     "B",
     "ATP binds a regulatory site (allosteric) to inhibit PFK-1 as a feedback signal."),
    # --- Bio/Biochem: cell_biology ---
    ("mcat::biobiochem::cell_biology",
     "Which organelle is the site of aerobic ATP production?",
     ["The nucleus", "The mitochondrion", "The ribosome", "The Golgi apparatus"],
     "B",
     "Oxidative phosphorylation occurs at the mitochondrial inner membrane."),
    ("mcat::biobiochem::cell_biology",
     "Ribosomes on the rough ER synthesize which proteins?",
     ["Cytosolic enzymes", "Secretory and membrane proteins", "Lipids", "tRNA molecules"],
     "B",
     "The rough ER makes proteins destined for secretion or membranes."),
    # --- Bio/Biochem: molecular_genetics ---
    ("mcat::biobiochem::molecular_genetics",
     "The lagging strand is made in fragments. What are they called?",
     ["Primers", "Okazaki fragments", "Introns", "Codons"],
     "B",
     "Discontinuous lagging-strand synthesis produces Okazaki fragments."),
    ("mcat::biobiochem::molecular_genetics",
     "DNA polymerase can only add nucleotides to which end?",
     ["The 5\u2032 end", "The 3\u2032 end", "Either end", "The middle"],
     "B",
     "Synthesis proceeds 5\u2032\u21923\u2032, adding to the free 3\u2032-OH end."),
    # --- Bio/Biochem: membranes ---
    ("mcat::biobiochem::membranes",
     "The Na\u207a/K\u207a ATPase pumps ions against their gradients. Transport class?",
     ["Facilitated diffusion", "Primary active transport",
      "Secondary active transport", "Simple diffusion"],
     "B",
     "It hydrolyzes ATP directly to move ions uphill: primary active transport."),
    ("mcat::biobiochem::membranes",
     "Glucose uptake coupled to the Na\u207a gradient is what kind of transport?",
     ["Primary active transport", "Secondary active transport",
      "Simple diffusion", "Endocytosis"],
     "B",
     "It uses the Na\u207a gradient (set up by the pump) as an energy source: secondary active transport."),
    # --- Psych/Soc: learning_memory ---
    ("mcat::psychsoc::learning_memory",
     "A dog salivates to a bell after it is paired with food. Conditioning type?",
     ["Operant", "Classical", "Observational", "Latent"],
     "B",
     "Pairing a neutral stimulus (bell) with an unconditioned stimulus (food) is classical conditioning."),
    ("mcat::psychsoc::learning_memory",
     "A rat presses a lever more often after receiving food. Conditioning type?",
     ["Classical", "Operant (positive reinforcement)", "Negative punishment", "Habituation"],
     "B",
     "Behavior increases because of a rewarding consequence: operant positive reinforcement."),
    ("mcat::psychsoc::learning_memory",
     "Studying in short sessions across a week beats cramming. Which effect is this?",
     ["Serial position", "The spacing effect", "State-dependent memory", "Priming"],
     "B",
     "Distributed practice outperforms massed practice: the spacing effect."),
    ("mcat::psychsoc::learning_memory",
     "Removing a chore when grades improve increases studying. Reinforcement type?",
     ["Positive reinforcement", "Negative reinforcement",
      "Positive punishment", "Negative punishment"],
     "B",
     "Removing an aversive stimulus to increase behavior is negative reinforcement."),
    # --- Psych/Soc: sensation_perception ---
    ("mcat::psychsoc::sensation_perception",
     "The dimmest light detectable half the time defines what?",
     ["The difference threshold", "The absolute threshold",
      "Weber's constant", "The signal criterion"],
     "B",
     "Detection 50% of the time defines the absolute threshold."),
    ("mcat::psychsoc::sensation_perception",
     "You need a bigger change to notice a difference in loud vs. soft sounds. Which law?",
     ["Weber's law", "Stevens' power law", "Fitts's law", "Bloch's law"],
     "A",
     "The just-noticeable difference is a constant proportion of the stimulus: Weber's law."),
    ("mcat::psychsoc::sensation_perception",
     "Receptors stop responding to a constant background smell. This is?",
     ["Sensitization", "Sensory adaptation", "Accommodation", "Retrieval failure"],
     "B",
     "Reduced response to an unchanging stimulus is sensory adaptation."),
    # --- Psych/Soc: cognition ---
    ("mcat::psychsoc::cognition",
     "Someone cannot use a coin as a screwdriver. Which bias is this?",
     ["Confirmation bias", "Functional fixedness", "Anchoring", "Framing"],
     "B",
     "Seeing an object only in its usual role is functional fixedness."),
    ("mcat::psychsoc::cognition",
     "Judging probability by how easily examples come to mind is which heuristic?",
     ["Representativeness", "Availability", "Anchoring", "Affect"],
     "B",
     "Ease of recall driving probability estimates is the availability heuristic."),
    # --- Psych/Soc: motivation_emotion ---
    ("mcat::psychsoc::motivation_emotion",
     "The Yerkes-Dodson law relates performance to what?",
     ["Reward size", "Arousal", "Sleep duration", "Age"],
     "B",
     "Performance is best at moderate arousal: the Yerkes-Dodson (inverted-U) law."),
    ("mcat::psychsoc::motivation_emotion",
     "The James-Lange theory says emotion follows what?",
     ["Cognitive appraisal", "Physiological arousal",
      "Simultaneous body and mind", "Social context"],
     "B",
     "James-Lange: we feel emotion because we notice bodily arousal (we're afraid because we tremble)."),
    # --- Psych/Soc: social_psychology ---
    ("mcat::psychsoc::social_psychology",
     "Blaming a late coworker's character rather than traffic illustrates what?",
     ["Self-serving bias", "The fundamental attribution error",
      "Actor-observer bias", "The just-world hypothesis"],
     "B",
     "Overattributing others' behavior to disposition is the fundamental attribution error."),
    ("mcat::psychsoc::social_psychology",
     "Liking a song more after hearing it repeatedly is which effect?",
     ["The mere-exposure effect", "Classical conditioning",
      "Social proof", "Cognitive dissonance"],
     "A",
     "Repeated exposure increasing liking is the mere-exposure effect."),
    ("mcat::psychsoc::social_psychology",
     "Individuals exert less effort in a group. Name the phenomenon.",
     ["Groupthink", "Social loafing", "Deindividuation", "Social facilitation"],
     "B",
     "Reduced individual effort in a group is social loafing."),
    # --- Psych/Soc: identity ---
    ("mcat::psychsoc::identity",
     "Being born into royalty is which kind of status?",
     ["Achieved", "Ascribed", "Master", "Role"],
     "B",
     "A status assigned at birth, independent of effort, is an ascribed status."),
    # --- Psych/Soc: demographics ---
    ("mcat::psychsoc::demographics",
     "Falling birth and death rates with industrialization describe what?",
     ["The Malthusian trap", "The demographic transition",
      "Urbanization", "Population momentum"],
     "B",
     "The shift to low birth and death rates as a society industrializes is the demographic transition."),
    ("mcat::psychsoc::demographics",
     "A population's age-sex breakdown is displayed with what tool?",
     ["A scatterplot", "A population pyramid", "An income histogram", "A life table"],
     "B",
     "Age-sex structure is shown with a population pyramid."),
]

# CARS reading passages. Each passage is original prose; each question is a
# 4-option MCQ across the four CARS skills (main_idea, inference, tone_argument,
# application). Rendered with the MCATCarsPassage notetype -> performance model.
# question tuple: (skill, question, [A, B, C, D], correct_letter, explanation)
CARS_PASSAGES: list[dict] = [
    {
        "title": "On the Persistence of Ruins",
        "passage": (
            "<p>Few sights unsettle the modern traveler quite like a ruin that refuses to be "
            "picturesque. We have inherited from the eighteenth century a comfortable habit of "
            "admiring decay from a safe distance: the ivy-clad abbey, the broken column framed by "
            "a painter's obliging sky. Such images flatter us. They suggest that time, however "
            "destructive, is also a kind of artist, softening the hard edges of human ambition into "
            "something we can contemplate without grief. But this consolation depends on a quiet "
            "dishonesty. The ruins we find beautiful are the ones that have finished dying. Their "
            "violence is safely in the past; their inhabitants are abstractions; and we are free to "
            "project onto their silence whatever melancholy pleases us.</p>"
            "<p>A more honest encounter begins where the picturesque ends. Consider the "
            "half-collapsed apartment block after an earthquake, or the shell of a library burned in "
            "a war still within living memory. These ruins have not yet been claimed by nature or by "
            "nostalgia. They remain stubbornly particular: this stairwell, that scorched ceiling, the "
            "ordinary objects fused to the floor. They resist the very generalization that makes older "
            "ruins comfortable. To stand before them is to be denied the luxury of distance, and it is "
            "precisely this denial, I want to argue, that gives them their peculiar moral force.</p>"
            "<p>The eighteenth-century taste for ruins was, at bottom, a taste for endings that "
            "confirmed a worldview. Decay proved the vanity of empires and, by implication, the "
            "wisdom of the observer who had seen through such vanity. The fresh ruin offers no such "
            "confirmation. It does not teach a lesson; it interrupts one. It insists that the loss is "
            "not yet metabolized into meaning, that someone's life was here and is not here now, and "
            "that no framing sky will arrange this fact into art. The discomfort we feel is not a "
            "failure of taste but the beginning of a more truthful attention.</p>"
            "<p>This is not an argument against beauty, nor a demand that we avert our eyes from "
            "older ruins. It is an argument about the order of operations. We are too quick to "
            "aestheticize, too eager to convert catastrophe into scenery. The recent ruin, by "
            "withholding its consolations, restores a sequence we habitually skip: first the fact of "
            "loss, then, perhaps, much later, the slow and always partial work of understanding.</p>"
            "<p>What the picturesque tradition mistook for wisdom was often only lateness&mdash;the "
            "ease of judging a wound after it has healed into a scar. The genuinely difficult task is "
            "to look at the wound. It is tempting to say that ruins teach us humility, but the older "
            "ones teach a humility that costs nothing. The fresh ruin asks for something harder: that "
            "we refuse the premature comfort of meaning, and stay, for a while, with what cannot yet "
            "be explained.</p>"
        ),
        "questions": [
            ("mcat::cars::main_idea",
             "Which of the following best captures the author's central claim?",
             ["Ancient ruins are inherently more beautiful than modern ones.",
              "Fresh, un-aestheticized ruins compel a more honest moral attention than picturesque ones.",
              "All ruins should be preserved as works of art.",
              "The eighteenth century understood decay better than we do."],
             "B",
             "The author argues the recent ruin's refusal of consolation gives it a peculiar moral force and provokes truthful attention."),
            ("mcat::cars::tone_argument",
             "The author's attitude toward the eighteenth-century 'taste for ruins' is best described as:",
             ["Admiring and reverent",
              "Neutral and purely descriptive",
              "Critical of its comfortable dishonesty",
              "Nostalgic and wistful"],
             "C",
             "Phrases like 'quiet dishonesty' and a humility that 'costs nothing' mark a critical stance."),
            ("mcat::cars::inference",
             "The author would most likely regard converting a recent catastrophe into 'scenery' as:",
             ["A necessary first response",
              "A premature evasion of loss",
              "Something that is impossible to do",
              "The proper role of artists"],
             "B",
             "The author faults our tendency to aestheticize 'too quickly,' skipping the fact of loss."),
            ("mcat::cars::inference",
             "By 'lateness,' the author most nearly means:",
             ["Arriving after an event has already started",
              "The ease of judging a wound after it has healed",
              "A simple failure of punctuality",
              "The gradual decline of empires"],
             "B",
             "The passage defines it directly as 'the ease of judging a wound after it has healed into a scar.'"),
            ("mcat::cars::application",
             "Which scenario best exemplifies the 'more honest encounter' the author endorses?",
             ["Photographing an ivy-covered abbey at sunset",
              "Sketching a Roman column for a landscape painting",
              "Standing silently in a recently bombed library without reaching for a lesson",
              "Writing a poem about the vanity of fallen empires"],
             "C",
             "The endorsed encounter attends to a fresh ruin without imposing premature meaning."),
            ("mcat::cars::tone_argument",
             "The phrase 'obliging sky' primarily serves to:",
             ["Praise the technical skill of landscape painters",
              "Suggest that the picturesque arranges reality to flatter the viewer",
              "Describe the typical weather at ruined sites",
              "Introduce a scientific claim about erosion"],
             "B",
             "'Obliging' implies the scene is composed to please the observer, part of the author's critique."),
        ],
    },
    {
        "title": "Who Keeps the Commons?",
        "passage": (
            "<p>For half a century, a single parable has dominated how we talk about shared "
            "resources. In its familiar form, it runs like this: imagine a pasture open to all. Each "
            "herder, acting rationally, adds another animal, since he gains the full benefit of the "
            "extra beast while the cost of overgrazing is spread among everyone. Multiply this logic "
            "across every herder and the pasture is destroyed. The lesson, we are told, is grim and "
            "universal: whatever is owned by all is cared for by none, and only private property or "
            "coercive regulation can save us from ourselves.</p>"
            "<p>The parable is elegant, memorable, and frequently wrong. Its error is not in its "
            "arithmetic but in its anthropology. It imagines human beings as isolated calculators, "
            "mute to one another, incapable of making or enforcing agreements. Yet the historical "
            "record is crowded with communities that managed shared pastures, fisheries, forests, and "
            "irrigation systems for centuries without either private ownership or a distant state. "
            "Swiss alpine villages, Japanese mountain commons, Spanish irrigation cooperatives&mdash;"
            "these were not utopias, but they were durable, and their durability demands "
            "explanation.</p>"
            "<p>What such communities possessed was not superior virtue but superior institutions. "
            "They set clear boundaries about who could use a resource and how much. They devised rules "
            "suited to local conditions rather than imported from a textbook. They monitored one "
            "another, often through arrangements in which the monitors were themselves users with a "
            "stake in honest reporting. Above all, they graduated their punishments: a first violation "
            "met a small sanction, a warning that preserved the relationship while signaling that the "
            "rule was real. Only repeated offenses drew serious penalties. This is not the behavior of "
            "isolated calculators; it is the behavior of neighbors who expect to meet again.</p>"
            "<p>The point is not that communities always succeed. Many commons have indeed collapsed, "
            "and the parable describes those collapses well. The point is that collapse is a contingent "
            "outcome, not a law of nature. Whether a shared resource is destroyed depends on whether "
            "the people who use it can communicate, trust, and hold one another accountable&mdash;"
            "capacities the original parable defined out of existence before the argument began.</p>"
            "<p>This matters because the parable has been used to justify sweeping policy. If ruin is "
            "inevitable, then the only question is which outside authority&mdash;the market or the "
            "state&mdash;should take the resource out of the users' hands. But if the users are capable "
            "of governing themselves, then dismantling their arrangements in the name of efficiency may "
            "destroy the very institutions that made stewardship possible. Well-meaning reforms have "
            "repeatedly done exactly this, replacing subtle local rules with blunt central ones and "
            "then citing the resulting disorder as proof that local control could never have worked.</p>"
            "<p>To take the commons seriously is therefore to resist a seductive simplicity. Human "
            "beings are not only the problem in the story; under the right conditions, they are also "
            "the solution. The task is not to choose between the market and the state as our two "
            "available saviors, but to ask what allows ordinary people, facing a shared and finite "
            "world, to bind themselves to rules of their own making.</p>"
        ),
        "questions": [
            ("mcat::cars::main_idea",
             "The primary purpose of the passage is to:",
             ["Prove that the tragedy of the commons never occurs",
              "Argue that communities can, under the right institutions, govern shared resources without markets or states",
              "Recommend privatizing all common resources",
              "Describe the daily life of Swiss alpine villages"],
             "B",
             "The passage's thesis is that self-governance of the commons is possible given the right institutions."),
            ("mcat::cars::tone_argument",
             "The author characterizes the classic parable as:",
             ["Entirely worthless and never accurate",
              "Elegant but resting on a flawed view of human nature",
              "A very recent invention",
              "Beyond any legitimate criticism"],
             "B",
             "The author calls it 'elegant, memorable, and frequently wrong,' locating the error 'in its anthropology.'"),
            ("mcat::cars::inference",
             "The discussion of graduated punishments suggests that successful commons depend on:",
             ["Harsh penalties for every first violation",
              "Ongoing relationships and repeated interaction among users",
              "Enforcement by a distant central state",
              "The elimination of all monitoring"],
             "B",
             "Graduated sanctions reflect 'neighbors who expect to meet again'\u2014ongoing relationships."),
            ("mcat::cars::application",
             "Which policy would the author most likely criticize?",
             ["Letting a fishing village set and enforce its own catch limits",
              "A national government abolishing a village's irrigation rules to impose one uniform system",
              "Neighbors monitoring one another's resource use",
              "Adapting resource rules to local conditions"],
             "B",
             "The author warns that replacing subtle local rules with blunt central ones can destroy working institutions."),
            ("mcat::cars::inference",
             "The author implies that documented collapses of some commons are:",
             ["Proof that the parable is a law of nature",
              "Evidence that local governance is always impossible",
              "Contingent failures rather than inevitable outcomes",
              "Fabricated by reformers"],
             "C",
             "The passage states that 'collapse is a contingent outcome, not a law of nature.'"),
            ("mcat::cars::tone_argument",
             "The phrase 'two available saviors' is best read as:",
             ["Sincere praise for the market and the state",
              "Ironic, questioning the assumption that only these two options exist",
              "A neutral, technical economic term",
              "A religious allusion meant literally"],
             "B",
             "The author uses it ironically to challenge the false choice between market and state."),
        ],
    },
    {
        "title": "The Discipline of Objectivity",
        "passage": (
            "<p>There is a persistent fantasy about what it would mean to write history objectively. "
            "In this fantasy, the ideal historian is a kind of transparent window: someone who has "
            "scrubbed away every preference, every loyalty, every trace of the present, so that the "
            "past may shine through undistorted. On this view, objectivity is a matter of subtraction. "
            "The more of himself the historian removes, the closer he comes to the truth. It is a "
            "noble image, and it is incoherent.</p>"
            "<p>It is incoherent because history is not found; it is made. The past does not arrive "
            "pre-sorted into significant and trivial events. An archive is not a narrative but a chaos "
            "of documents, most of them silent about the questions we most want to ask. To write "
            "history at all, the historian must select, and selection requires criteria, and criteria "
            "come from somewhere&mdash;from a sense of what matters, which is to say from a point of "
            "view. A historian without a point of view would not be supremely objective; he would be "
            "unable to begin. He would face the records of a century and have no reason to mention one "
            "thing rather than another.</p>"
            "<p>If objectivity cannot mean the absence of a viewpoint, what can it mean? The answer, I "
            "think, is that objectivity is not a starting condition but a discipline&mdash;a set of "
            "obligations one accepts precisely because one knows one has a viewpoint. The disciplined "
            "historian states her questions openly, so that readers can weigh them. She seeks out "
            "evidence that would embarrass her preferred conclusions, and reports it when she finds it. "
            "She distinguishes what the sources say from what she infers, and marks the difference. She "
            "allows the dead their strangeness, resisting the temptation to make them into early "
            "versions of ourselves. None of these obligations requires the impossible erasure of "
            "perspective. Each requires something harder: the honest management of perspective.</p>"
            "<p>Skeptics will object that this makes objectivity merely a matter of good manners, a "
            "style rather than a standard. But the obligations are not stylistic; they have teeth. A "
            "historian who suppresses inconvenient evidence can be caught and refuted by another "
            "historian working the same archive. The check on bias is not the individual's purity but "
            "the community's scrutiny. Objectivity, in this sense, is less like the transparency of a "
            "window and more like the fairness of a trial: it does not depend on jurors having no "
            "opinions, but on procedures that expose opinions to challenge.</p>"
            "<p>This reframing has a cost that its defenders should acknowledge. It means giving up the "
            "comfort of a final, view-from-nowhere account of the past, the definitive history that "
            "would make all others obsolete. What we get instead is a conversation that does not "
            "end&mdash;revisable, contested, and answerable to evidence. That may sound like a defeat. "
            "It is in fact the only version of objectivity that human beings, situated as we are in our "
            "own time and place, could ever honestly claim.</p>"
        ),
        "questions": [
            ("mcat::cars::main_idea",
             "The central thesis of the passage is that historical objectivity is best understood as:",
             ["The complete removal of the historian's viewpoint",
              "An impossible ideal that should simply be abandoned",
              "A discipline of honestly managing, rather than erasing, one's perspective",
              "Chiefly a matter of literary style"],
             "C",
             "The author redefines objectivity as a set of disciplined obligations that manage perspective."),
            ("mcat::cars::inference",
             "The author calls the 'transparent window' image incoherent chiefly because:",
             ["Real windows are never perfectly transparent",
              "Selecting what to write about necessarily requires a point of view",
              "Historians tend to dislike working in archives",
              "The past already arrives fully pre-sorted"],
             "B",
             "Since selection requires criteria and criteria come from a viewpoint, a viewpoint-free history cannot begin."),
            ("mcat::cars::tone_argument",
             "The author's stance toward the 'view-from-nowhere' account is that it is:",
             ["Achievable with sufficient effort",
              "A comforting but unattainable goal that must be given up",
              "The standard that all competent historians already meet",
              "Irrelevant to the practice of history"],
             "B",
             "The author says the reframing means 'giving up the comfort of a final, view-from-nowhere account.'"),
            ("mcat::cars::application",
             "Which practice best illustrates 'objectivity as discipline' as the author defines it?",
             ["Refusing to state one's research questions",
              "Ignoring evidence that undercuts one's thesis",
              "Reporting evidence that embarrasses one's preferred conclusion",
              "Portraying historical figures as if they were modern people"],
             "C",
             "Seeking and reporting inconvenient evidence is exactly one of the disciplined obligations named."),
            ("mcat::cars::inference",
             "The trial analogy is meant to show that the check on bias comes from:",
             ["The individual historian's personal purity",
              "Communal scrutiny and procedures that expose opinions to challenge",
              "The complete absence of opinions",
              "A single definitive account of the past"],
             "B",
             "Like a fair trial, objectivity depends on procedures and communal scrutiny, not on having no opinions."),
            ("mcat::cars::application",
             "A historian who 'allows the dead their strangeness' would most likely:",
             ["Assume medieval people shared modern moral values",
              "Interpret past actors on their own terms rather than as versions of us",
              "Avoid consulting archives altogether",
              "Refuse to draw any inferences at all"],
             "B",
             "The phrase means resisting the urge to make historical figures 'early versions of ourselves.'"),
        ],
    },
]
