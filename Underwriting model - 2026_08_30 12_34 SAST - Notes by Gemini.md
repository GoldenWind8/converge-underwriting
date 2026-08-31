# **✍️ Quick notes**

## **Underwriting model**

Aug 30, 2026  
[leec@wwib.co.za](mailto:leec@wwib.co.za) [Sashin Chetty](mailto:sashin@convergeai.co.za) [Cameron Chetty](mailto:cameron@convergeai.co.za)

Meeting discussions focused on developing a data-driven insurance pricing engine and establishing automated risk assessment methodologies.

## **Risk Assessment and Model Functionality**

* Cameron reviewed the needs analysis tool, which currently assesses 14 cover sections and 59 risk factors.  
* The system retains a history of previous underwriting assessments to inform future risk analysis tasks.  
* The model currently defaults to the highest severity rating within a category; the team will adjust the system to offset individual risk factors for more accurate band assessment.  
* Sashin identified that while the AI model is effective for language and risk understanding, it requires a separate logic layer for calculations to avoid inflating quotes.  
* Lee advised that 'Accounts Receivable' insurance is less relevant for modern, digitized businesses, suggesting the model parameters for this cover type require adjustment.

## **Pricing Engine Strategy**

* Cameron proposed separating the pricing engine from the LLM, using a formula based on sum insured, rate, and premium loading.  
* The engine will generate both a base premium and an adjusted (loaded or discounted) premium, accompanied by textual justifications for the rate variance.  
* Lee explained that insurers typically base premiums on risk surveys and specific loss history rather than solely on broad risk assessments.  
* The team plans to stress-test the system by running a low-risk policyholder profile to verify the output accuracy.

## **Future Scope and Expansion**

* The team discussed expanding the system to domestic insurance, which is less complex and relies primarily on building construction and loss history.  
* Lee committed to providing a list of niche insurance covers, such as 'Contractors All Risks' and machinery breakdown, to enhance the model's specialized capabilities.  
* The group intends to complete a proof-of-concept (POC) before presenting the system to external stakeholders for feedback.

## **Next steps**

- [ ] \[Lee Chetty\] Provide Base Rates: Submit a list of base rates for each insurance cover type in an Excel spreadsheet.  
- [ ] \[Lee Chetty\] Send Niche Covers: Compile and share a list of niche insurance cover types to inform the model analysis.  
- [ ] \[Cameron Chetty and Sashin Chetty\] Update Risk Assessment: Adjust the risk assessment model to calculate an accurate rating band by offsetting individual risk factors. Ensure the system stops defaulting to the highest severity rating per category.  
- [ ] \[Cameron Chetty and Sashin Chetty\] Build Pricing Engine: Develop a separate pricing engine that applies base rates, premium loadings, and discounts based on the risk assessment output. Ensure the system provides justifications for any rate adjustments using summary points.

**Want to see more?** [View the full notes]()  
Tip: You can always access your full notes from the left sidebar.

*You should review Gemini's notes to make sure they're accurate. [Get tips and learn how Gemini takes notes](https://support.google.com/meet/answer/14754931)*  
*How is the quality of **these specific notes?** [Take a short survey](https://google.qualtrics.com/jfe/form/SV_5bXzKQfylMIhSXc?confid=cn32EWF2L4UW_m8HfdJlDxIOOBEBMgUIigIgABgDCA&entryPoint=footerQuickNotes&isGoogler=False) to let us know your feedback, including how helpful the notes were for your needs.*

# **📝 Full notes**

Aug 30, 2026

## **Underwriting model**

Invited [leec@wwib.co.za](mailto:leec@wwib.co.za) [Sashin Chetty](mailto:sashin@convergeai.co.za) [Cameron Chetty](mailto:cameron@convergeai.co.za)

Attachments [Underwriting model](https://calendar.google.com/calendar/event?eid=MnJydGE4NDNsNjJ1YWpqa25iczQwMXJ0cGcgY2FtZXJvbkBjb252ZXJnZWFpLmNvLnph)

Meeting records [Transcript](https://docs.google.com/document/d/1a5ORWjC2Gk7NJ8cXZUtRhYn34-44P-By1nK89JQGGaw/edit?usp=drive_web&tab=t.hp8ao4o5qvf3) 

### **Summary**

Meeting discussions focused on developing a data-driven insurance pricing engine and establishing automated risk assessment methodologies.

**Risk assessment model capabilities**  
The system evaluates business risk using 14 categories and 59 factors, including features to customize severity ratings. This framework enhances underwriting accuracy by retaining historical assessment data for model improvement.

**Pricing engine development strategy**  
A dedicated pricing engine will be built to adjust premiums based on risk severity rather than relying on current flat rate models. This transition aims to provide data-backed justifications for premiums to insurers.

**System expansion and refinement**  
The platform will eventually incorporate niche insurance products and potential domestic coverage while phasing out outdated accounts receivable requirements. The primary decision was to initiate a proof of concept to validate model outputs.

### **Decisions**

## Aligned

* **Pricing engine architecture defined** The pricing engine will be developed as a separate, non-LLM calculation module that generates premiums by applying risk-adjusted loading or discounting to base rates.

* **Proof of concept validation strategy** The project will proceed with a proof of concept using dummy office quotes to demonstrate system capabilities and gather strategic feedback from Andy and Anish.

* **Accounts Receivable logic adjustment** Accounts Receivable coverage will only be flagged as a required insurance consideration for clients who maintain paper-based record-keeping systems.

### **Next steps**

- [ ] \[Lee Chetty\] Provide Base Rates: Submit a list of base rates for each insurance cover type in an Excel spreadsheet.

- [ ] \[Lee Chetty\] Send Niche Covers: Compile and share a list of niche insurance cover types to inform the model analysis.

- [ ] \[Cameron Chetty and Sashin Chetty\] Update Risk Assessment: Adjust the risk assessment model to calculate an accurate rating band by offsetting individual risk factors. Ensure the system stops defaulting to the highest severity rating per category.

- [ ] \[Cameron Chetty and Sashin Chetty\] Build Pricing Engine: Develop a separate pricing engine that applies base rates, premium loadings, and discounts based on the risk assessment output. Ensure the system provides justifications for any rate adjustments using summary points.

### **Details**

* **Risk Assessment and Needs Analysis Overview**: Cameron Chetty presented a risk assessment summary for a business client, covering 14 distinct sections and 59 risk factors. Key metrics included a 30 million rand building valuation, 3.6 million rand in gross profit, 3 million rand in office contents, and 2 million rand in accounts receivable. Lee Chetty reviewed the assessment, confirming that the needs analysis accurately captured the necessary considerations for a new client.

  ![][image1]

* **Risk Factor Assessment and Rating Customization**: Cameron Chetty detailed the assessment process, which identifies specific high-risk factors such as inadequate fire mitigation and uncertified electrical installations. Cameron Chetty explained that the system allows for the customization of severity ratings—categorized as low, medium, or high—allowing the user to adjust the program to fit specific business models if needed ([00:02:16](#00:02:16)).

  ![][image2]

* **System Memory and Continuous Improvement**: Cameron Chetty highlighted that the system retains a history of all assessments performed on potential clients. This "memory" feature allows the underwriting model to improve over time, as it learns how to better analyze risks and apply preferences based on previous, successful underwriting decisions ([00:04:28](#00:04:28)).

* **Current Insurance Quoting Limitations**: Lee Chetty clarified that the brokerage currently quotes premiums based on flat rates (e.g., a 4% fire rate) rather than incorporating comprehensive risk analysis at the initial stage. Lee Chetty explained that insurance companies typically conduct surveys to determine risk reduction requirements, such as installing fire extinguishers or sprinklers, after the quote is issued, and these requirements generally do not impact the premium itself ([00:05:31](#00:05:31)).

* **Proposed Pricing Engine Architecture**: Sashin Chetty and Cameron Chetty discussed building a separate pricing engine, distinct from the Large Language Model. The engine will calculate premiums by applying a loading factor or discount to a base rate based on the risk severity (low, medium, or high) generated by the underwriting assessment. This process will include a clear justification for any loading or discounting applied to the premium ([00:09:46](#00:09:46)).

* **Calibration with Dummy Data**: To support the development of the pricing engine, Lee Chetty agreed to provide base rates for each cover type (e.g., buildings combined, fire, business interruption) by sourcing dummy quotes from the office. This data will serve as a guideline for the model's initial testing ([00:13:29](#00:13:29)) ([00:18:03](#00:18:03)).

* **Justifying Premiums to Insurers**: Lee Chetty and Cameron Chetty discussed using the detailed risk assessment reports generated by the system to justify quoted premiums to insurers. They concluded that this provides a competitive advantage by allowing the brokerage to demonstrate that their premiums are based on a rigorous, data-backed risk analysis rather than arbitrary figures ([00:14:15](#00:14:15)).

  ![][image3]

* **Future Stakeholder Presentation**: The group agreed to proceed with a proof of concept. Once the team is satisfied with the system outputs, they plan to present the model to management, specifically Uncle Anish and Uncle Andy, to gather further input and demonstrate the value of the platform ([00:16:11](#00:16:11)) ([00:20:58](#00:20:58)).

* **Reviewing Accounts Receivable Coverage**: Lee Chetty identified that accounts receivable insurance is largely outdated for modern businesses that utilize digital records and cloud backups. Cameron Chetty proposed adjusting the system's parameters so that this coverage is only flagged as required if the business still relies on manual paper ledgers ([00:21:42](#00:21:42)).

  ![][image4]

* **Incorporating Niche Cover Products**: The group discussed the need to include niche insurance products, such as contractors' all risks and machinery breakdown, which are critical for specific business types like carpentry or manufacturing. Lee Chetty agreed to provide a list of these niche covers to ensure the model accounts for them ([00:23:44](#00:23:44)).

* **Data Security for Proof of Concept**: Cameron Chetty noted that for the immediate proof of concept, the team will keep the implementation simple. While they are using real policyholder data, they intend to bypass complex data security and protection protocols for the initial test phase ([00:25:40](#00:25:40)).

* **Potential for Domestic Insurance Expansion**: Lee Chetty and Cameron Chetty discussed the feasibility of extending the system to domestic insurance. Lee Chetty suggested that this would be a straightforward implementation as it primarily relies on building construction and loss history, similar to existing automated banking insurance products ([00:27:33](#00:27:33)).

* **Finalizing System Demo and Next Steps**: The team concluded the meeting by agreeing that Cameron Chetty and Sashin Chetty will work on the pricing engine logic, ensuring it properly offsets the highest-rated risk factor to avoid skewed results. Lee Chetty will provide the base rate list by the following day, and the team will plan a full system demonstration once the pricing engine is integrated ([00:29:22](#00:29:22)).

*You should review Gemini's notes to make sure they're accurate. [Get tips and learn how Gemini takes notes](https://support.google.com/meet/answer/14754931)*

*How is the quality of **these specific notes?** [Take a short survey](https://google.qualtrics.com/jfe/form/SV_5bXzKQfylMIhSXc?confid=cn32EWF2L4UW_m8HfdJlDxIOOBEBMgUIigIgABgDCA&detailLevel=standard&hasImages=True&entryPoint=footerMain&isGoogler=False) to let us know your feedback, including how helpful the notes were for your needs.*

# **📖 Transcript**

Aug 30, 2026

## **Underwriting model \- Transcript**

### **00:00:00**

**Cameron Chetty:** to allow for that so that um it doesn't just pull the the worst rating for a specific barrel and then it will basically offset it so we get a more accurate risk assessment.

**Sashin Chetty:** I see. I see. Okay. Okay. That makes sense. That makes

**Cameron Chetty:** Um okay cool. So effectively we looked across 14 different cover sections and identified 59 risk

**Sashin Chetty:** sense.

**Cameron Chetty:** factors. Okay. Uh then the first thing is a summary of what is required and why it's required. So we've got building buildings combined required reason the business owns building it operates from valued at 30

**Lee Chetty:** Okay.

**Cameron Chetty:** million rand fire required the business own significant assets including plant machinery stock and contents. Uh business interruption required the business generates 3.6 million in gross profit and depends on its machinery making it vulnerable to interruption. Uh office contents required the business owns 3 million in contents including desk chairs and canteen equipment. Glass not applicable. Uh accounts receivable required.

### **00:01:01**

**Cameron Chetty:** The business has debtors of 2 million rand which would be at risk if the electronic records were lost. Fidelity insurance required. A single employee authorizes payments creating an exposure to employee dishonesty. Uh theft required. Business holds valuable stock. Money required. Okay. So basically everything was Yeah.

**Lee Chetty:** Let me see. Good intensive request. Thanks person. Mhm.

**Cameron Chetty:** Tell me scroll down and

**Lee Chetty:** Where can Cam? Yeah.

**Cameron Chetty:** then umbrella was worth considering.

**Lee Chetty:** Yeah. Yeah.

**Cameron Chetty:** So just based on your knowledge,

**Lee Chetty:** Okay.

**Cameron Chetty:** how did how did the needs analysis go? It's looking right.

**Lee Chetty:** Looks to be in order. Yeah, it's actually telling you I mean from from a new client perspective, it's telling you you you put in all the information on

**Sashin Chetty:** Would

**Lee Chetty:** the company and it's telling you basically what you need to consider and why.

**Cameron Chetty:** Yeah.

**Lee Chetty:** Yeah.

**Sashin Chetty:** you say it's like missing anything or it's too much

### **00:02:16**

**Cameron Chetty:** Yeah.

**Lee Chetty:** No, no. I I I think that's at the moment the way I see it,

**Sashin Chetty:** or

**Lee Chetty:** it's it's it's to the tea.

**Cameron Chetty:** That's good to Yeah.

**Sashin Chetty:** Okay.

**Cameron Chetty:** Uh, cool. So then if and then once once it you go into like okay what are the required cover types then we actually go into a

**Lee Chetty:** Yeah.

**Cameron Chetty:** risk factor assessment. So for each section we look at okay buildings combined what were the what were the high risk factors here. So in inadequate fire mitigation uh uncertified electrical installation uh acid concentration on a single location. Uh and then it it quotes from the submission, you know, what was stated that that that led it to to this outcome.

**Lee Chetty:** Yeah. Yeah, because there's chemical liquids and chemicals.

**Cameron Chetty:** Yeah. Yeah. So, this assessment's done. I mean, it's this is quite in-depth now. So,

**Lee Chetty:** Yeah.

**Cameron Chetty:** um it goes into each of the cover types, fire, uh business interruption.

### **00:03:12**

**Cameron Chetty:** So, if you were going to pull out anything or perhaps maybe what we can look to do is just do um a large my dad love.

**Sashin Chetty:** It's also

**Cameron Chetty:** Yeah. Hi again.

**Sashin Chetty:** me.

**Cameron Chetty:** Bye. Bye.

**Lee Chetty:** Where are you off to? Sunday afternoon.

**Cameron Chetty:** To jump.

**Lee Chetty:** Oh, okay.

**Cameron Chetty:** Thank you.

**Lee Chetty:** Enjoy.

**Cameron Chetty:** Yeah. Um so I mean this goes quite in depth um in terms of in terms of the the for each each section right each of the cover sections. Uh and then it actually just highlights okay why so for example goods in transit and there's no nominated drivers. Okay. Unspecified vehicle roots, vehicle tracking in place. So we've assigned a rating. So medium severity, low severity, medium severity. So maybe uh I mean and and kind of the the point of it is that this this could adjust depending on how you guys want to to rate these factors. So if you feel like okay having no non-nominated drivers is not actually a medium severity maybe it's low severity then we can actually program it so that for your business models it's it's a low it's a low severity risk.

### **00:04:28**

**Cameron Chetty:** Uh and then beyond that um every time you run something through the system it keeps a history of how you've assessed a potential policy holder or potential client. And when you when you start working on somebody new, it pulls from that history of okay, how were the risks considered? How were they analyzed? What was considered beyond what was on the initial scope and and why was it considered? So it keeps it keeps a memory effectively a memory of all of those things. And uh the next time you have to run someone through the underwriting model, you'll find it's closer to um to the way that you want to actually underwrite this policy holder uh and and and how you want to go about doing the needs analysis. So we can improve this in any way that you tell us. Uh uh but yeah.

**Lee Chetty:** What what I'm thinking now, right? Okay. Def you you put all this together.

**Cameron Chetty:** So

**Lee Chetty:** You say you're your your the next uh level now would be obviously to input premium to quote

### **00:05:31**

**Cameron Chetty:** will be too.

**Lee Chetty:** on a premium.

**Cameron Chetty:** Yeah. Yeah. I mean if you're comfortable with this with this.

**Lee Chetty:** No. Well, well, what I'm saying is look,

**Cameron Chetty:** Yeah.

**Lee Chetty:** this is giving you all the information you based on the information that you inputed in terms

**Cameron Chetty:** Yeah.

**Lee Chetty:** of the client.

**Cameron Chetty:** Yeah.

**Lee Chetty:** You're now giving us giving me the cut the the the cover that's required. You're also telling me the the validia risk reduction uh uh the risk reduction requirements which which is

**Cameron Chetty:** Yeah.

**Lee Chetty:** good. So I'm saying if if what I want to do is basically you are going to you guys are going to put now a premium based on this on this business right I'm going to ask the office also on that same quote to the question I

**Cameron Chetty:** Yeah.

**Lee Chetty:** mean that the information I sent to get a quote from the office and I want to compare that

**Cameron Chetty:** Yeah.

**Lee Chetty:** quote to the quote that you're going to generate to see how far off we are in terms of quoting

### **00:06:43**

**Cameron Chetty:** Yeah. So but but but then what what we need some assumptions there. What what are what are the input assumptions?

**Lee Chetty:** You know, you you you you've put your quote,

**Cameron Chetty:** Yeah.

**Lee Chetty:** then I'm going to see whether your quote is more or less in line with

**Sashin Chetty:** Um,

**Lee Chetty:** what?

**Cameron Chetty:** But F but but okay how I think we need to understand. So when you take

**Lee Chetty:** See, we okay, let me let me put you this way,

**Cameron Chetty:** the

**Lee Chetty:** right? We don't quote based on all this kind of information at the

**Cameron Chetty:** Yeah.

**Lee Chetty:** onset. We work on rates. If I get a quote quote request, I just go rates, you know, I mean, if if it's a fire, we might say, okay, fire rate is 4% and we quote it accordingly. We don't we don't take all the the uh the

**Cameron Chetty:** Yeah.

**Lee Chetty:** risk requirements into consideration,

**Cameron Chetty:** Yeah.

**Lee Chetty:** right? We just quote a straight premium.

**Cameron Chetty:** Yeah.

### **00:07:36**

**Lee Chetty:** The only time basically something might uh uh be a problem is the insurance company would send out a survey here and when the survey goes out he will survey the risk and he will come back to us with risk reduction requirements. Most of the time it doesn't affect the premium.

**Cameron Chetty:** Yeah.

**Lee Chetty:** It's just basically putting the just getting the risk in order.

**Cameron Chetty:** Yes.

**Lee Chetty:** You know I mean if you go

**Cameron Chetty:** So that so that if you are coding point 4 for Maya it's they have enough mitigation in place that it becomes reasonable for them to quote at

**Lee Chetty:** That's what I'm saying.

**Cameron Chetty:** point4.

**Lee Chetty:** It's like they they'll take they'll use that rates and then if if a survey goes out, he comes back and you say,"Well, but most of the time it's not based on the premium. It's based on the risk itself." He tell us,"We need fire extinguishers.

**Cameron Chetty:** Yeah.

**Lee Chetty:** We need uh your your fire extinguishers haven't been serviced in the last two years. That needs to be sorted out.

### **00:08:30**

**Lee Chetty:** We need maybe sprinkler a sprinkler system if if the risk area is more

**Cameron Chetty:** Yeah.

**Lee Chetty:** than,500 square meters you know I mean things like that.

**Cameron Chetty:** Yeah.

**Lee Chetty:** So they'll come fire host wheels you mean I'm talking only I'm talking personally know in terms of fire I mean so they'll come back and then they'll give us like 30 days in which to get

**Cameron Chetty:** Yeah.

**Lee Chetty:** things sorted out and then we ask the client to to to implement tremendous risk reduction requirements and if that is done then the risk is accepted and I mean all

**Sashin Chetty:** Um,

**Cameron Chetty:** Yeah.

**Sashin Chetty:** so just just one thing just in terms of what we were initially building and and what this

**Lee Chetty:** Good.

**Sashin Chetty:** would be. Uh so so we were what what the AI models are good at is kind of like uh language understanding and so that's what made it a good good um option for assessing like risk because it's mostly language understanding when it gets into the calculations it can be done but

**Lee Chetty:** Thank you.

**Sashin Chetty:** it's not so especially in this case where there's a bit of ambiguity my thinking if if I were to just put this raw like like this into the model and try to get like an amount for a quote it's probably going to give us something like 20,000 is probably going to add like 5,000 per section.

### **00:09:46**

**Sashin Chetty:** Everything's going to get taken into account because there's like a lot of things here. It's just going to give like a high amount. And I think that's what it's always going to do unless there's some sort of

**Cameron Chetty:** So my thinking is that we actually we build the pricing engine separate.

**Sashin Chetty:** stress

**Cameron Chetty:** So we don't actually have to use the the LLM in that step. But uh the way I understand it is that uh Dad, you've got specified rates that you're going to apply to the different cover types, right?

**Lee Chetty:** Hm. Mhm.

**Cameron Chetty:** Okay. Uh I think maybe what we could do is have that as an input.

**Lee Chetty:** Yeah.

**Cameron Chetty:** So if you if you uh have it on hand and you can say okay for each of the cover types this is the rate that I want to quote at you just put that.

**Lee Chetty:** Well, it'll be a guideline, right?

**Cameron Chetty:** Yeah.

**Lee Chetty:** Because obviously what we could possibly do thereafter depending on the uh on on on also

### **00:10:25**

**Cameron Chetty:** Yeah.

**Lee Chetty:** the previous loss history you know I mean if he's at a a very high loss history

**Cameron Chetty:** Yeah.

**Lee Chetty:** and it's not running very profitably obviously you need to load but then it

**Cameron Chetty:** Then you must then you must you must load the you must load that rate. Yeah.

**Lee Chetty:** must your the system must be able to generate uh a discount as well as a loaded loading you know I mean so we can say okay

**Cameron Chetty:** A a loaded rate. Yeah.

**Lee Chetty:** your the system generates ated a,000 rand premium, but we feel it's a little too low, we're going to load it by 25%. Or your,000 rand is a little too high,

**Cameron Chetty:** Yeah.

**Lee Chetty:** we want to discount it by

**Cameron Chetty:** Okay. So, so I think what how how we take that into consideration here Sashin is if um we if if

**Lee Chetty:** 25%.

**Cameron Chetty:** from we run the model we get the output we get the risk assessment per cover type right so I think the one the one step first thing we need to work on is like crediting the risk assessment for risk mitigation so that the the highest risk factor doesn't automatically push the band into highest or highest severity right so we have the severity um credited with the with the different risk mitigation factors okay depending depending on the the band that that comes out as.

### **00:11:37**

**Cameron Chetty:** If it's low risk, if it's uh medium risk, high risk, okay, that's going to impact influence the pre uh the effectively the loading that we're going to apply to the base rate. We'll have a base rate set for every single cover type. Then depending on the the risk severity of the overall class that's that's being insured, we'll apply the the the premium loading uh and then we'll we'll quote two figures the base the base uh rate and the loaded rate and with a reason as to why the the rate was loaded pulling from the output from the underwriting system saying this risk was rated as medium and um in quick summary bullet points um this is this is what rated the risk as medium that make sense and then we show and then we show base the base uh

**Lee Chetty:** Yeah. Yeah.

**Cameron Chetty:** premium and we show the loaded premium

**Lee Chetty:** Correct. Yeah. And and and and you feel it's a good it's an exceptionally good risk.

**Cameron Chetty:** Yeah.

**Lee Chetty:** Your base premium is there and you can you you can discount it and say the reason why you discounted it.

### **00:12:39**

**Sashin Chetty:** Um.

**Lee Chetty:** So basically what we saying s is that we have our base base premium.

**Cameron Chetty:** Yeah.

**Lee Chetty:** If if if if your your system generates that this is a high risk then you're going to you're going

**Sashin Chetty:** Mhm.

**Lee Chetty:** to load your premium and you're going to say why you're loading your premium.

**Sashin Chetty:** Mhm.

**Lee Chetty:** And if you if your system generates this is a very low risk from your base premium you're going to discount it and say why you've discounted it.

**Sashin Chetty:** Okay. Okay. That makes sense. That

**Cameron Chetty:** and and that's that's fairly simple Sashin. We don't actually I mean there's there's no LLM step in that.

**Sashin Chetty:** makes

**Cameron Chetty:** That's just a pure calculation engine and it's it's as simple as saying sum insured times uh sum in short times rate times by loading premium

**Sashin Chetty:** Yeah. Yeah. Makes sense. That makes sense.

**Cameron Chetty:** loading.

**Sashin Chetty:** Um, and so in terms of that guideline, is that something you guys have like as a document or is

### **00:13:29**

**Lee Chetty:** I can I can I I can do what I'm going to do based on the same this test that we're doing now.

**Sashin Chetty:** it

**Lee Chetty:** I'm going to get the office to just give me a dummy quote, right? So they'll they'll put the rates for each section that we've we've requested like say your buildings combined the 30 million what rate they'll charge and the fire and so forth.

**Sashin Chetty:** okay?

**Lee Chetty:** I'll get that from the office just on a on a guideline and then maybe we could use that to

**Sashin Chetty:** Okay.

**Lee Chetty:** to a step

**Sashin Chetty:** And and just out of curiosity,

**Lee Chetty:** one.

**Sashin Chetty:** for example, like the section buildings combined, would you get a rate for that? Is it going to be like a flat rate regardless of the value? Like in this case, it's 30 million.

**Lee Chetty:** Yeah. Yeah. It's straightforward.

**Sashin Chetty:** So even and even even if it was like a 100 million,

**Lee Chetty:** So we we go straight with

**Sashin Chetty:** it would still be the same same rate.

### **00:14:15**

**Cameron Chetty:** Yeah. So that's what I'm saying,

**Sashin Chetty:** Okay.

**Cameron Chetty:** Sashin.

**Lee Chetty:** correct.

**Cameron Chetty:** The calculation engine or the pricing engine is actually quite simple.

**Sashin Chetty:** I see. Yeah.

**Cameron Chetty:** Um from from a broker's perspective because they they're just quoting on rates. You're taking summer short times rate times my

**Lee Chetty:** Yeah.

**Cameron Chetty:** premium.

**Lee Chetty:** You see but but insurers would quote differently you know I

**Sashin Chetty:** Oh,

**Cameron Chetty:** Yeah. And the show will have a full pricing

**Lee Chetty:** mean they would look at Yeah. insurer will look at your your risk,

**Cameron Chetty:** regimen.

**Sashin Chetty:** perfect.

**Lee Chetty:** how you you you you um what what you've estimated this risk to be, whether it's low, high, or medium, and then they will rate according to that because they are the ones.

**Cameron Chetty:** Yeah.

**Lee Chetty:** But we as brokers, we try to get the best possible premium for our client.

**Cameron Chetty:** Yeah. No, exactly. So what you could what you what you could at the end end up doing that is that even if you you can show actually show um um like once the pricing is done for for a specific policy holder with the with the risk adjustments and and stuff in place.

### **00:15:17**

**Cameron Chetty:** uh when you actually show give that to the insurer you I mean they they can see that as a report saying hey this

**Lee Chetty:** Yeah.

**Cameron Chetty:** is the rate charging this is this is the risk assessment this is what was uh considered in in

**Lee Chetty:** Yeah.

**Cameron Chetty:** in the um the quoting yeah or the pricing process

**Lee Chetty:** Pricing. Yeah.

**Cameron Chetty:** and and and this is why you should give us this

**Lee Chetty:** No, 100%.

**Cameron Chetty:** premium

**Lee Chetty:** That's what I'm saying is basically we we saying to insurers we are in a position to justify the the rates that we've charged for them to like kind of accept it,

**Cameron Chetty:** Yeah. Yeah.

**Lee Chetty:** you know, and we can tell them we didn't just base our our premium.

**Cameron Chetty:** Yeah.

**Lee Chetty:** We we've taken all this into consideration and this is the premium we've we've come to which we can justify you. So,

**Cameron Chetty:** Yeah.

**Lee Chetty:** so they going to have a problem in terms of accepting the premium as well.

**Cameron Chetty:** And you think the office has scope to use this fix?

### **00:16:11**

**Lee Chetty:** Yeah. Yeah. Once we once we put the scene together and I speak to the powers at hand and

**Cameron Chetty:** Yeah,

**Lee Chetty:** you can see I mean also you know it it's it's also good to to put you know

**Cameron Chetty:** because um

**Lee Chetty:** it uh is for an insurer to look at this as well because to them they can give it to all the baron kind of you

**Cameron Chetty:** yeah.

**Lee Chetty:** know

**Cameron Chetty:** So I mean I'm I'm comfortable to do that even even like within Westwood. I mean, if they um I mean, but I'll speak to I mean, if once we get it right and and you're comfortable for us to present to Uncle Anish and Uncle Andy, uh then yeah, you let me know and then I mean, there's a lot there's probably a lot more we could do uh for the brokerage beyond underwriting. Um just cuz yeah, we can do anything.

**Lee Chetty:** Yeah. Yeah. Well, let's try this.

**Cameron Chetty:** Um yeah.

**Lee Chetty:** Let's let's work on this.

### **00:17:08**

**Lee Chetty:** Get an idea. Then then we can perhaps look at doing a presentation to them and see how

**Cameron Chetty:** Yeah, I'm happy with that.

**Lee Chetty:** how they they they they value it.

**Cameron Chetty:** Yeah,

**Sashin Chetty:** That sounds good. That sounds

**Lee Chetty:** Yeah,

**Sashin Chetty:** good.

**Lee Chetty:** you don't have to go into too much of ind depth because at this stage is just

**Cameron Chetty:** that's a proof of concept.

**Lee Chetty:** uh yeah and then if if if they're happy you know I mean then then obviously you

**Cameron Chetty:** Yeah. Yeah. Yeah.

**Lee Chetty:** can you can invest more time and whatever you know mean from your side but the first first step is perhaps to get get someone to say hey I like what you're doing here and what we'd like to improve on and then see you know I mean obviously if once they

**Cameron Chetty:** Yeah. Yeah. Yeah. Exactly.

**Lee Chetty:** say I like what you're doing Then basically that's one step ahead, one step through the door. uh where then thereafter you're going to you're going to generate something to their liking which will be

### **00:18:03**

**Cameron Chetty:** Yeah,

**Lee Chetty:** accepted.

**Cameron Chetty:** for sure. I mean, that's that's that's the plan. Um, so I think the the pricing piece is fine. I mean, that's simple.

**Lee Chetty:** Yeah.

**Cameron Chetty:** It's easy enough to do. Maybe what you do is just send us your base rate uh on on each of the the cover types. uh like just you know to put in a list maybe an Excel an Excel spreadsheet just cover type rate uh cover type rate cover type rate cover type rate as the base rate um and then uh maybe just maybe just put it into bands. So say if it's good risk, low risk, medium risk, high risk and then put there like what your what you're

**Lee Chetty:** Like I said, son,

**Cameron Chetty:** loading.

**Lee Chetty:** we don't we don't generally look at it from a risk point of view, you know. I mean,

**Cameron Chetty:** Yeah.

**Lee Chetty:** but this is basically I've used a shoe factory which is kind of a high risk compared to most of the other covers. I mean, other businesses out there because your your sugar I mean your sho your your shoe company you're dealing with leather,

### **00:18:50**

**Cameron Chetty:** Yeah.

**Lee Chetty:** you're dealing with fabric that's very like combustible material that you got there. Plus in addition to that you've got all your your chemicals and your flammable liquids and stuff like you know I mean so so those are

**Cameron Chetty:** Yeah. Yeah.

**Lee Chetty:** like it's more on the high risk which which is it's come through correctly rated as an iris but I know you've not only took the the company itself and based the high risk you've taken the information in terms of what um firefighting equipment they have and all that stuff to to establish high risk.

**Cameron Chetty:** Yeah. Yeah.

**Lee Chetty:** Uh but but if you take the high like take that compare that

**Cameron Chetty:** But I I mean the wristband

**Lee Chetty:** to like even if you take another company which is basically like let's say it's a uh let's say it's it's it's it's a cupboard company you dealing with a with with let's say it's a it's a cupboard you know kitchen kitchen cupboard a carpentry company where there's lots of wood sawdust and which is a high risk you know in terms fire and stuff.

### **00:20:02**

**Cameron Chetty:** Yeah.

**Lee Chetty:** So those are things that like generally is an exclusion by most insurance companies. They like it's not part of the appetite to ensure these kind of

**Cameron Chetty:** Yeah.

**Lee Chetty:** risks.

**Cameron Chetty:** May maybe what we could also do that is is um it's just that kind of stress test the system in a bit but u we can come up with a polic like a policy holder that's um very very low risk or almost like a good risk in a way um run it through and see if we also come out at at a good risk.

**Lee Chetty:** and the rates in terms of that company compared to high risk like like um

**Cameron Chetty:** Yeah. Yeah.

**Lee Chetty:** a carpentry company or

**Cameron Chetty:** Yeah. So so may Yeah. So maybe what what we do is um just

**Lee Chetty:** no but I think based on this at the moment Sashin I think if if you can put rates you put something along this let's work on this as test test one,

**Cameron Chetty:** Okay.

**Lee Chetty:** right?

### **00:20:58**

**Lee Chetty:** And then we'll uh once we generate something like from here then maybe if if it's all making sense and I have a I chat to to Andy and Anes and uh see how they they look at it maybe we can have a meeting like this a team meeting as well you guys can they can give

**Cameron Chetty:** Yeah.

**Lee Chetty:** their input as to what they think you know I mean different to what I'm thinking and then

**Cameron Chetty:** Yeah. Yeah.

**Lee Chetty:** we can see from there.

**Cameron Chetty:** Okay. Cool. That sounds good

**Sashin Chetty:** Um, cool, cool.

**Cameron Chetty:** then.

**Sashin Chetty:** So, um, we'll you'll give us the you'll get the cover, the

**Lee Chetty:** I'll give you I'll give I'll give you all the rate tomorrow.

**Cameron Chetty:** Yeah.

**Lee Chetty:** I'll pass it on to Cameron tomorrow.

**Cameron Chetty:** Yeah. The Yeah. base rates.

**Sashin Chetty:** quoted.

**Cameron Chetty:** Then uh once you have that that quote from the office on this dummy client

**Lee Chetty:** Yeah. Well, what I'll do is I'll just phone in tomorrow morning.

### **00:21:42**

**Lee Chetty:** I'll speak to Amanda or Sashin. I'll just get a like I'll ask them what's the base rate of the useful buildings combined for fire for business interruption.

**Sashin Chetty:** Okay.

**Lee Chetty:** There's one thing that that's come up here where you're suggested here is uh your accounts receivable. Now in today's day and age, most companies don't use accounts receivable because accounts receivable was back in back in the

**Cameron Chetty:** What's that?

**Lee Chetty:** old days where they had books of ledger where they they they wrote all the stuff onto into a book because there were no computers and

**Sashin Chetty:** What's

**Lee Chetty:** stuff and that book got lost. they lost all the the dattors.

**Cameron Chetty:** Yeah.

**Sashin Chetty:** that?

**Lee Chetty:** So they used to insure against that to to to recover the money that they may have lost because they lost their book of dats. So they don't know how much you know I mean now everything is computerized and is backed.

**Cameron Chetty:** Yeah.

**Lee Chetty:** So if anything happens even the business goes down for example they still the datas still remain because it's either out you know backed up in cloud or they've got out out of premises backup so they can still recover the money your dattors will still pay

### **00:22:51**

**Cameron Chetty:** Yeah.

**Lee Chetty:** them. So accounts receivable is not something that we generally none of my policies at the moment that we've sold to accounts receivable. People don't generally buy unless you still back in the day using a ledger to

**Cameron Chetty:** Yeah.

**Sashin Chetty:** Okay.

**Cameron Chetty:** So may maybe what we can do is we leave it in but we adjust the parameter so that it's only

**Lee Chetty:** write

**Cameron Chetty:** considered required if they still use paper trail uh on the accountable.

**Lee Chetty:** it. Yeah. Yeah.

**Cameron Chetty:** Yeah.

**Lee Chetty:** Yeah.

**Sashin Chetty:** Um, and yeah, um, I was just going to ask these cover names, do they somewhat match the names of the actual covers or

**Lee Chetty:** Yeah. Yeah. Your glass, your fidelity cover,

**Sashin Chetty:** the

**Lee Chetty:** your t theft, money, goods and transit. Can I can I move this or you move electronic business orders,

**Cameron Chetty:** Uh yes, I'll move

**Sashin Chetty:** Oh.

**Cameron Chetty:** it.

**Lee Chetty:** group personal accent, stated benefits, motor traders, public liability, broke from liability. Yeah.

### **00:23:44**

**Lee Chetty:** Then then there's also other covers like but it's it's niche products like contractors all risks. But that's you can look at that different like if it's a if it's a building contractor for example, you'll want to offer a contractor's all risk policy to cover the contracts that they're working on against

**Cameron Chetty:** So, so I think that's that's that'll be useful face if um if you just give us a list of even the niche cover

**Lee Chetty:** uh

**Cameron Chetty:** types then uh what we can do is we

**Lee Chetty:** I think I think Sashin I think the one document that I sent through to you some time back I think it was it's not the needs analysis was it the needs analysis I think I think it's on my

**Cameron Chetty:** You said you only sent us the needs analysis on the niche

**Lee Chetty:** needs analysis is it not there no it's all Hey,

**Cameron Chetty:** copy types. I don't think because

**Lee Chetty:** contractors.

**Cameron Chetty:** this

**Lee Chetty:** Okay, but I'm going to send you a list of specific covers like contractor's orders.

**Cameron Chetty:** Yeah.

### **00:24:35**

**Lee Chetty:** Uh then then you you can have an engineering policy like for a for example for this uh shoe company. they could have uh one machine that that is the art of the business, you know, I mean and if that machine motor packs up or some specific on that machine packs up and they now have

**Cameron Chetty:** Yeah.

**Lee Chetty:** to import the the stuff from say India or China or something which is going to take long and is going to obviously affect the operation of the business.

**Cameron Chetty:** Yeah.

**Lee Chetty:** You can ensure against the parts firstly and then you can ensure against uh loss of profits following machinery breakdown. Understand? Yeah.

**Cameron Chetty:** Yeah.

**Lee Chetty:** So those are all the some of the niche products that can be brought in in terms of specific cover to a to a type of business where a business relies heavily on the

**Sashin Chetty:** Let's

**Lee Chetty:** machinery for production that needs to come in like machinery breakdown. Machinery breakdown or deterioration uh or or business interruption following

**Sashin Chetty:** see.

**Lee Chetty:** machinery breakdown.

### **00:25:40**

**Sashin Chetty:** Um, is all of this like documented somewhere or is it some of it like also just in your head?

**Lee Chetty:** I I can send I can send I can send you stuff that that that gives

**Sashin Chetty:** Um,

**Lee Chetty:** you all the specifics that you could you could you could you know I mean you could you

**Sashin Chetty:** okay. Okay. Yeah.

**Lee Chetty:** obviously know which like certain types of businesses needs to pull through all that kind of information or that kind of risk to give them

**Sashin Chetty:** I see.

**Cameron Chetty:** Yeah. Yeah. So,

**Sashin Chetty:** Yeah.

**Cameron Chetty:** so where where niche products need to be considered,

**Lee Chetty:** Yeah.

**Cameron Chetty:** we like we the model will also consider them and included in the cover analysis and then the pricing engine can also pull I mean uh can can pull from that. So, okay, cool. Um, yes, I think for for PC purposes, Sash, I mean, that's that's simple enough for us to do. Um, without us like going into the detail of security, you know, poppy up personal information protection, those those kind of data security and data protection um standards that we we need to apply because we're using real policy holder data.

### **00:26:46**

**Cameron Chetty:** Uh so I think just for the purpose of the PC I mean that's that should be fairly simple for us to show end to end.

**Lee Chetty:** Yeah.

**Cameron Chetty:** Um so yeah we can work on that. Um, just send us Tell us anything you think will be relevant

**Lee Chetty:** Let me let me let me see from my side tomorrow.

**Cameron Chetty:** and

**Lee Chetty:** Let me send you some base rates to work on and I'll send you all the the niche

**Cameron Chetty:** yeah, right.

**Lee Chetty:** products that can also be you I mean uh somehow brought into a set kind of business to to offer specialized risks the specialized risks as well you

**Cameron Chetty:** Yeah, for sure. For sure.

**Lee Chetty:** know.

**Cameron Chetty:** For sure. All right, cool.

**Lee Chetty:** I can send it to you tomorrow.

**Cameron Chetty:** That's No,

**Lee Chetty:** Just give me tomorrow. Maybe between tomorrow and by Wednesday.

**Cameron Chetty:** no, it's fine. You take take your time when whenever you can get it and you're ready.

**Lee Chetty:** Yeah,

**Cameron Chetty:** You're not too worried.

### **00:27:33**

**Lee Chetty:** I'd like I like to get it to you guys as soon as possible and you can work on something. But tomorrow I'm sure I'll be able to get some

**Cameron Chetty:** Yeah. Okay.

**Lee Chetty:** base.

**Cameron Chetty:** Sure. I mean, we can also like we can even extend this to to beyond just doing the commercial risk assessment. We can even do like domestic policy or straightforward.

**Lee Chetty:** I must think it would be straightforward,

**Cameron Chetty:** Yeah.

**Lee Chetty:** you I mean that would be a quick one because that domestic input the information well domestic domestic it should be something like this way I'll tell you where we just put

**Cameron Chetty:** Yeah.

**Lee Chetty:** the the domestic insurance you know I mean the domestic information and you know there there's no risk risk to consider yet basically what you need on a domestic is straightforward

**Cameron Chetty:** Yeah.

**Lee Chetty:** input the information it gives you a premium based on previous loss

**Cameron Chetty:** Yeah.

**Lee Chetty:** history that's all You don't need you don't need to know okay the

**Cameron Chetty:** Okay.

**Lee Chetty:** only thing you need to know that basically that needs to take into consideration is like your the construction of your building whether it's straight brick and tile whether there's no uh taps because taps will obviously increase the rating you know but that's straightforward it's nothing and that might be a good one to to work with as well because it's

### **00:28:35**

**Cameron Chetty:** Yeah.

**Lee Chetty:** straightforward if I I if we implement something like that office they basically do is in client forms da put all the information give you a premium same time looking for the

**Cameron Chetty:** Heat.

**Lee Chetty:** client.

**Cameron Chetty:** Yeah. Yeah, we can do that. Um,

**Lee Chetty:** Yeah.

**Cameron Chetty:** so yeah, I mean, so I think maybe for PC, well, we can explain that that domestic is much simpler. Uh, and it's a quick system, but I think I think what Sorry,

**Lee Chetty:** Yeah.

**Cameron Chetty:** Sash,

**Sashin Chetty:** Oh, no.

**Cameron Chetty:** what what do you want to say?

**Sashin Chetty:** I was just going to say just out of curiosity, domestic is like me getting insurance on my house.

**Cameron Chetty:** Yeah. Yeah. Yeah.

**Sashin Chetty:** Oh.

**Cameron Chetty:** It's not not commercial.

**Sashin Chetty:** Uh, okay.

**Cameron Chetty:** Yeah.

**Sashin Chetty:** Oh, and that stuff like kind of already exists, right? Like I see in my banking app that I can just put in my details and get like a insurance quote.

**Lee Chetty:** Perfect.

**Cameron Chetty:** Yeah.

### **00:29:22**

**Sashin Chetty:** Okay.

**Cameron Chetty:** Yeah.

**Sashin Chetty:** Okay.

**Cameron Chetty:** So, so it's the same thing,

**Sashin Chetty:** Okay.

**Cameron Chetty:** but now we effectively a software that the brokerage can just use quickly and and quickly pump out a coach if they need

**Sashin Chetty:** Okay. Okay. Cool. Cool.

**Cameron Chetty:** to.

**Sashin Chetty:** Cool. Cool. Um, thank you. Thank you. That was very insightful. And yeah, thank you for helping us

**Lee Chetty:** Thank you guys. Yeah,

**Sashin Chetty:** out.

**Lee Chetty:** I wish you all the best and uh let's hope we

**Cameron Chetty:** Yeah, thanks. Uh we when we when okay once we we're comfortable with the outputs and like the the um

**Lee Chetty:** can

**Cameron Chetty:** like you know the end state of it. Then I we'll actually take you through a full demo of you know using the system and and like obviously we want to make it as simple and easy to use as possible and not it's going to be quick to implement quick to get a result.

### **00:30:13**

**Cameron Chetty:** Um yeah so that's that's the intention and then yeah after we do that and we're comfortable we we'll also build in that that pricing that that like small pricing engine if that's that's simple enough s from my understanding and then um yeah and then

**Sashin Chetty:** Yeah.

**Cameron Chetty:** we

**Sashin Chetty:** Yeah. I think if as long as I have that and like those base risks, I mean B base B amount,

**Cameron Chetty:** bas yeah easy enough because because the only thing we're pulling from from the

**Sashin Chetty:** then that should be simple enough. Well,

**Cameron Chetty:** output report is effectively just the the over the over over over the overall risk assessment for for the cover type or for the cover section.

**Sashin Chetty:** Makes sense.

**Cameron Chetty:** Yeah.

**Sashin Chetty:** Makes

**Cameron Chetty:** Um yeah. So it's just we just need to work on the um on offsetting that that risk assessment so it doesn't just

**Sashin Chetty:** sense.

**Cameron Chetty:** take the highest rated risk for the category um which is what it's currently doing. Um and then yeah and then I think we'll I mean because then we get an accurate rating band assessment and then we just have to apply the appropriate premium loading.

### **00:31:15**

**Sashin Chetty:** Okay, sounds good. Sounds good.

**Cameron Chetty:** All right Sash I think I should have taken over the family business here.

**Lee Chetty:** Yeah.

**Sashin Chetty:** What's the family business?

**Lee Chetty:** Yeah.

**Cameron Chetty:** Insurance broking

**Sashin Chetty:** Oh, I see. I see. Wait, this Uncle Andy, is that your your guys family?

**Cameron Chetty:** No,

**Lee Chetty:** Cool.

**Cameron Chetty:** no, no, no, no.

**Sashin Chetty:** Oh. Oh.

**Cameron Chetty:** That's That's ex bosses.

**Sashin Chetty:** Oh, I see. I see. I see. I

**Cameron Chetty:** Yeah.

**Sashin Chetty:** see.

**Cameron Chetty:** All right. Sh. Thank you,

**Lee Chetty:** Okay, my boy.

**Cameron Chetty:** Dad.

**Lee Chetty:** Thanks Sashin.

**Sashin Chetty:** Oh,

**Lee Chetty:** Thanks for your time.

**Sashin Chetty:** yeah. Thanks, YouTube. Thanks,

**Lee Chetty:** You guys have a good weekend,

**Sashin Chetty:** YouTube.

**Lee Chetty:** rest of your weekend.

**Cameron Chetty:** Thanks.

**Lee Chetty:** Yeah,

**Sashin Chetty:** YouTube.

**Lee Chetty:** we'll we'll touch base again during the course of the week perhaps.

**Sashin Chetty:** All right. Found good script.

**Cameron Chetty:** Yeah.

### **00:32:00**

**Sashin Chetty:** Goodbye.
