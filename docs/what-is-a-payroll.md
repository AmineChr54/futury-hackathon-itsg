 What a payroll program is

A payroll program (Entgeltabrechnungsprogramm) is the software employers use to pay their staff, for example SAP HR, DATEV or Lexware. Each month it:

      - Calculates pay: gross to net, income tax, and social insurance contributions (health, pension, unemployment and long-term care insurance), applying contribution ceilings and similar rules.
      - Tracks absences: sick leave, maternity leave and so on, and works out how long the employer must keep paying wages (up to 6 weeks of sick pay).
      - Reports to the authorities electronically: in Germany employers can't just fill in a paper form. The payroll software must generate standardised fixed-width data files, like TEEL0-Test1-DBVO, and send them to the health insurers and other institutions. That's the 800 million messages a year.

      Those files feed directly into benefit decisions. For example, the health insurer calculates an employee's sickness benefit from the pay data the employer's software sends. So §95b SGB IV says only system-tested programs may send them, and ITSG is the body that does the testing.

      Example testing workflow, using the prior-illness case

      1. Pick a requirement. The tester takes the prior-illness rule from the Verfahrensbeschreibung §3.12. A request (submission reason 41) may only be sent if:
      - the current sick leave is certified,
      - there was certified sick leave in the previous 6 months,
      - the total comes to at least 30 days.

      2. Design a test case. The tester writes a scenario with fixed inputs and a known correct output. Employee Peter Mustermann:
      - has 4 past sick-leave periods (July, October and December 2025, and March 2026 on paper only),
      - is now off sick from 11.03.2026,
      - leaves the company on 31.03.2026.

      The expected output is a DSLW record with submission reason 41 and a DBVO block listing all 4 periods, newest first, with the insurer-only fields left empty.

      3. The vendor runs it in their software. Someone at, say, DATEV creates this fictional employee in the payroll program, enters the sick-leave periods, and runs payroll. The software decides by itself whether to generate a prior-illness request and what to put in it.

      4. Collect the output. The software produces the data file. That's exactly what TEEL0-Test1-DBVO is.

      5. Check the output against the expected result. Today an ITSG examiner does this by hand:
      - Is the submission reason 41?
      - Are all 4 periods there, in the right order?
      - Are the dates correct?
      - Are the fields only the insurer may fill left empty?
      - Is the format valid (lengths, padding, encoding)?

      6. Test the follow-up steps. The scenario continues:
      - The insurer replies that it doesn't have the March note.
      - The employer sends a pay certificate with sick pay ending 30.03.
      - The insurer later confirms the March period.
      - The employer must cancel the first certificate (submission reason 88) and send a corrected one with sick pay ending 27.03.

      The tester checks that the software handles each step correctly, including linking the IDs between messages.

      7. Run negative tests. For example, with only 20 days of sick leave in total, the software must refuse to generate a prior-illness request. Producing one would be a failure.