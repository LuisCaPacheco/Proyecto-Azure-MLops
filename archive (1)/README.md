ENAPE 2021: National Survey on Educational System Access and Retention in Mexico (Cleaned and Adapted Dataset)


# What is the ENAPE?
The ENAPE (National Survey on Access and Permanence in Education) is a crucial survey conducted by INEGI (National Institute of Statistics and Geography). Its purpose is to generate detailed statistical information about the educational characteristics of the Mexican population, specifically concerning access, enrollment, and permanence within the National Educational System (SEN).

The ENAPE's main objective is to provide valuable data for the formulation of public educational policies, academic research, and to generally enhance society's understanding of the country's educational landscape.


# What kind of information does ENAPE collect?

The ENAPE gathers a wide range of information, including, but not limited to:

* Target Population: Generally focuses on a specific age range (e.g., 0 to 29 years old, as in the ENAPE 2021).

* School Enrollment: Identifies the population enrolled in different school cycles and educational levels (preschool, elementary, middle school, high school, higher education).

* Access to Education: Analyzes the reasons why some individuals have never attended school or did not enroll in a specific school cycle.

* School Permanence and Dropout: Investigates the reasons for not completing an educational level or dropping out of studies. This is crucial for understanding the barriers and challenges students face.

* Attendance Modality: May include information on whether attendance is in-person, remote, or blended.
Technological Resources at Home: In recent editions (like ENAPE 2021), relevant information on the availability of devices such as smartphones, computers, tablets, and internet in households has been included. This is fundamental for understanding the digital divide and distance education.

* School Support: Identifies who provides support to students in their school activities (e.g., parents, guardians, private tutors).

* Perception of Education: May include questions about informants' valuation of education.


# Possible Uses and Research Questions

Understanding Educational Access and Permanence:
1. Dropout Prediction and Analysis
2. Impact of Household Resources on Education
3. Role of Support Systems

Exploring the Learning Environment:
1. Technology's Role in Learning
2. Evaluation Methods and Student Outcomes

Socio-Emotional Well-being and Education:
1. Mental Health Impacts
2. Perception of Education's Value

Policy and Regional Insights
1. Regional Disparities
2. Effectiveness of School Entry Programs

Modeling and Advanced Analytics:
1. Clustering and Segmentation
2. Feature Importance


# File Contents and Data Structure
The information is organized to provide a comprehensive overview of the survey conducted by INEGI in 2021.

df01: This first file contains the sociodemographic and equipment characteristics of the surveyed households, providing the housing context for the data.

df02: Complementing df01, this second file delves into the specific details of each enrolled individual within those households. It covers relevant aspects of their educational situation, access to resources, and study modalities. Together, both files enable a robust analysis of the interaction between housing conditions and individuals' educational experiences.

df03: This third file is the result of a strategic merge between df01 (household characteristics) and df02 (characteristics of the enrolled individual). This fusion was performed using the unique household identifier (FOLIO) as the key, allowing us to link household information with that of each person living and studying in it. The resulting shape of df03 is (32343, 67).
This particular configuration aims to facilitate an in-depth study where the individual is the primary subject of analysis. By joining these datasets in this manner, we can explore how household characteristics directly influence the educational and personal experiences of each student.

It's important to note that if your research goal is to analyze household characteristics in isolation or as the primary focus, it's recommended to use the df01 file directly. Alternatively, if you need to combine both data sources for a household-centric study, merging df01 and df02 might require a different methodology, tailored to your analysis's logic. The final choice will always depend on the analyst's criteria and the specific objectives of each investigation.

Data cleaning and feature selection were performed based on criteria of importance, impact, and relevance.


# Features

## Household Type Dataset Features (df01 variables)
FOLIO: Household identifier number
q_personas: Number of people living in the household
q_hombres: Number of men living in the household
q_mujeres: Number of women living in the household
x<30: Number of people under 30 years old living in the household
pc: Household has a desktop computer
laptop: Household has a laptop computer
tv_plana: Household has a flat-screen digital television
tablet: Household has a tablet (touchscreen device)
smartphone: Household has a smartphone
InternetF: Household has a fixed internet connection
sIF_causa: Reason why they are Without Fixed Internet
Values: Due to lack of economic resources; Not interested or don't need it; Doesn't know how to use it; Unaware of its usefulness; Inadequate or incapable equipment; No service in their locality (lack of infrastructure); Has internet access in other places; For reasons related to privacy or security; Other reason; No response.
mejora_vida: Level of confidence that education improves the standard of living
mejora_trabajo: Level of confidence that education improves job opportunities
mejor_decisor: Level of confidence that education influences making better life decisions
ENT: Federal Entity (State)
FACTOR: Expansion Factor (also known as weight or sample weight). This refers to the number of units in the total population that each sampled unit represents in the survey.

## Individual Dataset Features (df02 variables and combined in df03)
FOLIO: Household identifier number
SEXO: Gender (Male or Female)
EDAD: Age of the enrolled individual
edu_inicial: Educational Level: Early Childhood Education (Daycare/Nursery)
inscrito: Enrolled in the past school year (2020-2021)?
nivel_edu: Grade (level) of studies in which they were enrolled
terminado: Did they complete (finish) the grade in which they were enrolled last school year (2020-2021)?
nt_causa: Main reason why they did not complete the school period
Values: Due to lack of money or resources; Had to work or started working; Lack of interest or aptitude for school (didn't want to or didn't like it); Failed subject(s), semester, or year, or due to low academic performance; School closure or it was far away; Physical or mental disability; Due to the COVID-19 pandemic; Got sick with COVID-19; Illness or physical or emotional health problems (heart conditions, cancer, depression, or anxiety); Got engaged, married, or became pregnant (the person or their partner); Had to dedicate time to household chores or caring for a family member; Family or parents didn't let them continue studying; Personal problems (family conflicts, partner, classmates, friends); Other.
asesorias: Took tutoring or additional classes at school
extraord: Took an extraordinary exam (second chance)
recursado: Had to retake a module or a subject
ev_tareas: In their school, homework, projects, or research work were evaluated
ev_exam: In their school, evaluation was done with oral or written exams
ev_digital: In their school, evaluation was done with videos, photographs, or audio as evidence
ev_partcp: In their school, evaluation was done with participation or presentations during class
ev_libreta: In their school, their notebook notes, copies, or book were evaluated
ev_asist: In their school, attendance was evaluated
ev_otro: In their school, evaluation was done in another way
ev_nula: There was no evaluation in their school
inscrito_actual: The individual is enrolled for the current school year (2021-2022)
nins_causa: Causes for not enrolling in the current school year (2021-2022)
entr_diagnost: Upon entering their school, some educational assessment or diagnosis is performed
entr_induccion: Upon entering their school, some introductory course is held
entr_regulariz: Upon entering their school, extra remedial classes are considered
m_impresos: Printed or written material is used in their classes (books, encyclopedia, magazines, photocopies)
m_pizarra: Whiteboard, marker board, or electronic board is used in their classes
m_audio_vid: Audiovisual material is used in their classes (videos, movies, audios)
m_expos: Presentations are used in their classes
m_otro: Other types of didactic material are used in their classes
med_plataform: Digital platforms were used in their classes (e.g., Google Classroom, Aplicate, Moodle)
med_mail_RS: Email and/or social media were used in their classes
med_clases_v: Virtual classes were used in their classes (e.g., Google Meet, Teams, Zoom)
med_presencial: Assignments were submitted in person in their classes
t_smartphone: For school homework or projects, smartphones were used
t_laptop: For school homework or projects, a laptop or notebook computer was used
t_PC: For school homework or projects, a desktop computer was used
t_tablet: For school homework or projects, a tablet (touchscreen device) was used
t_TV: For school homework or projects, a digital television (flat screen) was used
t_impresos: For school homework or projects, printed didactic material was used
t_mama: For school homework or projects, support was received from mother
t_papa: For school homework or projects, support was received from father
t_fam_mujer: For school homework or projects, support was received from a female family member
t_fam_hombre: For school homework or projects, support was received from a male family member
t_o_mujer: For school homework or projects, support was received from a non-family female
t_o_hombre: For school homework or projects, support was received from a non-family male
t_horas: Number of hours per week dedicated to school homework or projects
max_nivel_esp: Highest education level of father, mother, or guardian
estres: The individual has suffered from stress due to current educational conditions
depresion: The individual has suffered from depression or sadness due to current educational conditions
desespero: The individual has suffered from despair due to current educational conditions
antisocial: The individual has suffered from problems socializing due to current educational conditions
ENT: Federal Entity (State) (1 - Aguascalientes, ..., 32 - Zacatecas)
FACTOR: Expansion Factor (also known as weight or sample weight). This refers to the number of units in the total population that each sampled unit represents in the survey.


# Key to Variable Encodings
For variables concerning confidence levels (mejora_vida, mejora_trabajo, mejor_decisor):
1 represents "strongly agree"
2 represents "somewhat agree"
3 represents "slightly agree"
4 represents "not at all agree"
9 represents "don't know"

For the SEXO variable:
1 represents "male"
2 represents "female"

Throughout the dataset, for binary (yes/no) features with values 1, 2:
1 represents "yes"
2 represents "no"

Throughout the dataset, for features with values 1, 2, 9:
1 represents "yes"
2 represents "no"
9 represents "don't know"

Complementary Excel files are attached for some categorical features. These files share the same variable names as in the dataset.


## DISCLAIMER: Important Note on Data Usage
This dataset is a processed and adapted version of the original data published by INEGI. It's provided solely to facilitate easier access and understanding for informational or exploratory purposes. This dataset does not replace or substitute INEGI's official releases. For the complete, official data and corresponding methodology, please visit the INEGI website directly at: www.inegi.org.mx.

The use, analysis, and interpretation of this processed data are the sole responsibility of the user. If you use this resource for projects, visualizations, or publications, we kindly request that you cite INEGI as the original source and this repository as the adaptation source.


## Cite and Share!
If this work proved useful to you, please consider giving it an upvote. Your support not only acknowledges the effort to disseminate and reuse public data, but it also helps this valuable resource reach a wider audience. Every upvote makes a difference!


"Created by RENE CARDOSO"