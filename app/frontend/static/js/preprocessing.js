/* =======================================================
   preprocessing.js  – JS extracted from preprocessing.html
   Phase 6.1-6.2: Split Monolithic Templates
   
   Server data is consumed from window.__PREPROCESSING_DATA
   which is set by the inline data-bridge in preprocessing.html.
   ======================================================= */

"use strict";

const PREP_DATA = window.__PREPROCESSING_DATA || {};

/* ──────────────────────────────────────────────────────────
   Model Selector (Jinja2 data consumed via data bridge)
   ────────────────────────────────────────────────────────── */
function initModelSelector() {
    const availableModels = PREP_DATA.availableModels || {};
    const serverSelect = document.getElementById("server_ollama_input");
    const modelSelect = document.getElementById("llmSelect_ollama_input");
    if (!serverSelect || !modelSelect) return;

    function updateModels() {
        const selectedServer = serverSelect.value;
        const models = availableModels[selectedServer] || [];

        modelSelect.innerHTML = "";

        models.forEach(model => {
            const option = document.createElement("option");
            option.value = model;
            option.textContent = model;
            modelSelect.appendChild(option);
        });

        const option = document.createElement("option");
        option.value = "llama3.1:8b";
        option.textContent = "llama3.1:8b";
        option.selected = true;
        modelSelect.appendChild(option);
    }

    serverSelect.addEventListener("change", updateModels);
    updateModels();
}

/* ──────────────────────────────────────────────────────────
   Label Topic Toggle
   ────────────────────────────────────────────────────────── */
function initLabelTopicToggle() {
    const toggle = document.getElementById("enableLabelTopic");
    if (!toggle) return;
    toggle.addEventListener("change", function () {
        const block = document.getElementById("labelTopicOptions");
        if (block) block.style.display = this.checked ? "block" : "none";
    });
}

/* ──────────────────────────────────────────────────────────
   LLM Type Visibility (ollama / GPT)
   ────────────────────────────────────────────────────────── */
function initLLMTypeVisibility() {
    const selectType = document.getElementById("llmSelect_type");
    const geminiDiv = document.getElementById("llmSelect_gemini");
    const ollamaDiv = document.getElementById("llmSelect_ollama");
    const ollamaServer = document.getElementById("server_ollama");
    const gptDiv = document.getElementById("llmSelect_gpt");
    const gptApiKey = document.getElementById("gptApiKey");
    if (!selectType) return;

    function show(el) { if (el) { el.classList.add("d-flex"); el.classList.remove("d-none"); } }
    function hide(el) { if (el) { el.classList.remove("d-flex"); el.classList.add("d-none"); } }

    function updateVisibility() {
        const value = selectType.value;

        if (value === "GPT") {
            hide(geminiDiv); hide(ollamaDiv); hide(ollamaServer);
            show(gptDiv); show(gptApiKey);
        } else if (value === "ollama") {
            hide(geminiDiv); hide(gptDiv); hide(gptApiKey);
            show(ollamaDiv); show(ollamaServer);
        } else if (value === "gemini") {
            show(geminiDiv);
            hide(ollamaDiv); hide(ollamaServer); hide(gptDiv); hide(gptApiKey);
        } else {
            hide(geminiDiv); hide(ollamaDiv); hide(ollamaServer); hide(gptDiv); hide(gptApiKey);
        }
    }

    updateVisibility();
    selectType.addEventListener("change", updateVisibility);
}

/* ──────────────────────────────────────────────────────────
   Progress Bar helper
   ────────────────────────────────────────────────────────── */
function updateProgressBar() {
    // Called after successful stage operations; relies on
    // step*Done flags set during stage processing.
    // Currently a placeholder — the progress bar is updated
    // by polling preprocess_status in the future.
}

/* ──────────────────────────────────────────────────────────
   Stage 1: Data Preprocessing
   ────────────────────────────────────────────────────────── */
let db_selected = "";
let step1Done = false, step2Done = false, step3Done = false;
let currentSubStep = 1;
const totalSubSteps = 3;

function initStepModal() {
    const modal = document.getElementById('stepModal');
    if (!modal) return;

    const modalTitle = modal.querySelector('.modal-title');
    const bodyBase = document.getElementById('modal-body-base');
    const bodyOne = document.getElementById('modal-body-1');
    const bodyTwo = document.getElementById('modal-body-2');
    const footerBase = document.getElementById('modal-footer-base');
    const footerTwo = document.getElementById('modal-footer-2');
    const prevButton = document.getElementById('prevStep2');
    const nextButton = document.getElementById('nextStep2');

    // Step 1
    const datasetPreprocessButton = document.getElementById('confirmDatasetPreprocess');

    function Stage1Selection() {
        const selector = document.getElementById("optionsDatasets1");
        const dbSelected = selector.value;

        const textColumnInput = document.getElementById("TextColumn-Segmentor");
        const idColumnInput = document.getElementById("IdColumn-Segmentor");
        const OutputPathInput = document.getElementById("TextColumnOutput-Segmentor");
        const minLengthInput = document.getElementById("MinimumLength-Segmentor");
        const separatorInput = document.getElementById("Separator-Segmentor");

        const defaultMinLength = 100;
        const defaultSeparator = "\n";

        const srcLang = document.getElementById('SourceLanguage').value;
        const tgtLang = document.getElementById('TargetLanguage').value;
        const isMonolingual = tgtLang === 'mono';

        if (dbSelected !== "" && textColumnInput !== "" && idColumnInput !== "") {
            db_selected = dbSelected;
            step1Done = true;

            const textColumn = textColumnInput.value.trim();
            const idColumn = idColumnInput.value.trim();
            const OutputPath = OutputPathInput.value.trim();
            const minLength = minLengthInput.value ? parseInt(minLengthInput.value) : defaultMinLength;
            const separator = separatorInput.value;

            const segmentor_data = {
                "output": OutputPath,
                "text_col": textColumn,
                "id_col": idColumn,
                "min_length": minLength,
                "sep": separator,
                "src_lang": srcLang,
                "tgt_lang": isMonolingual ? "" : tgtLang
            };

            // For monolingual, translator_data is not used (backend will detect via .monolingual marker)
            const translator_data = isMonolingual ? null : {
                "output": OutputPath,
                "text_col": textColumn,
                "lang_col": document.getElementById('LanguageColumnTranslator').value.trim(),
                "src_lang": srcLang,
                "tgt_lang": tgtLang
            };

            const preparer_data = {
                "output": OutputPath,
                "src_lang": srcLang,
                "tgt_lang": isMonolingual ? "" : tgtLang,
                "is_monolingual": isMonolingual,
                "schema": {
                    "chunk_id": "id_preproc",
                    "doc_id": idColumn,
                    "text": textColumn,
                    "full_doc": "full_doc",
                    // For monolingual: the segmenter always writes a 'lang' column.
                    // For bilingual: use the user-supplied language column name.
                    "lang": isMonolingual ? "lang" : document.getElementById('LanguageColumnTranslator').value.trim(),
                }
            };

            const data = {
                'dataset': db_selected,
                'segmentor_data': segmentor_data,
                'translator_data': translator_data,
                'preparer_data': preparer_data
            };

            console.log(isMonolingual ? '[MONOLINGUAL MODE]' : '[BILINGUAL MODE]', data);

            // Disable button and show spinner
            datasetPreprocessButton.disabled = true;
            const originalHTML = datasetPreprocessButton.innerHTML;
            datasetPreprocessButton.innerHTML = `
                <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                Processing...
            `;

            fetch("/preprocess/Stage1", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data),
            })
                .then(response => {
                    if (!response.ok) {
                        return response.json().then(err => {
                            throw new Error(err.message || `HTTP Error: ${response.status}`);
                        });
                    }
                    return response.json();
                })
                .then(response => {
                    console.log('Success (' + response.status + '): ' + response.message);
                    updateProgressBar();

                    const select2 = document.getElementById('optionsDatasets2');
                    const select3 = document.getElementById('optionsDatasets3-2');
                    const newOption = document.createElement('option');

                    newOption.value = OutputPath;
                    newOption.text = OutputPath;

                    select2.appendChild(newOption);
                    select3.appendChild(newOption.cloneNode(true));

                    // Re-enable button
                    datasetPreprocessButton.disabled = false;
                    datasetPreprocessButton.innerHTML = originalHTML;
                })
                .catch(error => {
                    console.error("Error in Fetch/AJAX:", error.message);
                    showToast(`Couldn\'t start new Preprocess process because ${error.message}`);
                    // Re-enable button on error
                    datasetPreprocessButton.disabled = false;
                    datasetPreprocessButton.innerHTML = originalHTML;
                });
        } else {
            step1Done = false;
            showToast('Please select an available dataset before accepting.');
        }
    }

    // Hide/show slide 3 (Translator) based on monolingual selection
    const targetLangSelect = document.getElementById('TargetLanguage');
    if (targetLangSelect) {
        targetLangSelect.addEventListener('change', function () {
            const isMonolingual = this.value === 'mono';
            const slide3 = document.getElementById('slide-3');
            const slide3Nav = document.querySelector('[data-slide="3"]') || document.querySelector('.step-indicator:nth-child(3)');
            const translatorBadge = document.getElementById('translator-step-indicator');

            if (slide3) {
                if (isMonolingual) {
                    slide3.style.opacity = '0.4';
                    slide3.style.pointerEvents = 'none';
                    // Show an inline notice
                    let notice = slide3.querySelector('.monolingual-notice');
                    if (!notice) {
                        notice = document.createElement('div');
                        notice.className = 'monolingual-notice alert alert-info mt-2';
                        notice.innerHTML = '<i class="bi bi-info-circle me-1"></i><strong>Monolingual mode:</strong> Translation will be skipped automatically.';
                        slide3.prepend(notice);
                    }
                } else {
                    slide3.style.opacity = '';
                    slide3.style.pointerEvents = '';
                    const notice = slide3.querySelector('.monolingual-notice');
                    if (notice) notice.remove();
                }
            }
        });
    }

    if (datasetPreprocessButton) {
        datasetPreprocessButton.addEventListener('click', Stage1Selection);
    }

    // Click on boxes
    const stepBoxes = document.querySelectorAll('.step-box');

    function showCorrectModalBody(event) {
        const stepNumber = event.currentTarget.dataset.step;
        const targetId = 'modal-body-' + stepNumber;

        const allModalBodies = document.querySelectorAll('[id^="modal-body-"]');
        allModalBodies.forEach(body => { body.style.display = 'none'; });

        const targetBody = document.getElementById(targetId);
        if (targetBody) targetBody.style.display = 'block';

        // Buttons Next & Prev Slides only on step 1
        if (document.getElementById('modal-body-1').style.display != "none") {
            if (stepNumber == 1) {
                document.getElementById('nextSlide').style.display = 'block';
                document.getElementById('prevSlide').style.display = 'none';
            } else if (stepNumber == 2) {
                document.getElementById('nextSlide').style.display = 'block';
                document.getElementById('prevSlide').style.display = 'block';
            } else if (stepNumber == 3) {
                document.getElementById('nextSlide').style.display = 'none';
                document.getElementById('prevSlide').style.display = 'block';
            } else {
                document.getElementById('nextSlide').style.display = 'none';
                document.getElementById('prevSlide').style.display = 'none';
            }
        } else {
            document.getElementById('nextSlide').style.display = 'none';
            document.getElementById('prevSlide').style.display = 'none';
        }

        const stepModalLabel = document.getElementById('stepModalLabel');
        if (stepNumber == 1) {
            stepModalLabel.textContent = 'Step 1: Preprocess info';
            document.getElementById('confirmDatasetPreprocess').style.display = 'none';
            document.getElementById('confirmTopicModelling').style.display = 'none';
            document.getElementById('confirmDownload').style.display = 'none';
        } else if (stepNumber == 2) {
            stepModalLabel.textContent = 'Step 2: Topic Modeling info';
            document.getElementById('confirmDatasetPreprocess').style.display = 'none';
            document.getElementById('confirmTopicModelling').style.display = 'block';
            document.getElementById('confirmDownload').style.display = 'none';
        } else if (stepNumber == 3) {
            stepModalLabel.textContent = 'Step 3: Download info';
            document.getElementById('confirmDatasetPreprocess').style.display = 'none';
            document.getElementById('confirmTopicModelling').style.display = 'none';
            document.getElementById('confirmDownload').style.display = 'block';
        }
    }

    stepBoxes.forEach(box => {
        box.addEventListener('click', showCorrectModalBody);
    });
}

/* ──────────────────────────────────────────────────────────
   Stage 2: Topic Modeling
   ────────────────────────────────────────────────────────── */
function initStage2() {
    const btn = document.getElementById("confirmTopicModelling");
    if (!btn) return;

    btn.addEventListener("click", function () {
        const dataset = document.getElementById("optionsDatasets2").value;
        const outputPath = document.getElementById("outputPath2").value.trim();
        const lang1 = document.getElementById("lang1").value;
        const lang2El = document.getElementById("lang2");
        const lang2 = lang2El ? lang2El.value : "";
        const kTopics = document.getElementById("kTopics").value;

        if (!dataset || !outputPath || !lang1 || !kTopics) {
            showToast("Please fill in all required fields before continuing.");
            return;
        }

        // For bilingual: lang1 and lang2 must differ
        if (lang2 && lang1 === lang2) {
            showToast("Lang1 and Lang2 cannot be the same. For monolingual, select 'N/A (Monolingual)'.");
            return;
        }

        let labelTopic = {};
        if (document.getElementById("enableLabelTopic").checked) {
            const llm_type = document.getElementById('llmSelect_type').value;
            let llm_model = "";
            let gpt_api = "";
            let ollama_server = "";
            if (llm_type === "gemini") {
                llm_model = document.getElementById("llmSelect_gemini_input")?.value || "gemini-2.5-flash";
            } else if (llm_type === "ollama") {
                llm_model = document.getElementById("llmSelect_ollama_input").value;
                ollama_server = document.getElementById('server_ollama_input').value;
                if (!llm_model || !ollama_server) {
                    showToast('Select an Ollama LLM and server.');
                    return;
                }
            } else if (llm_type === "GPT") {
                llm_model = document.getElementById("llmSelect_gpt_input").value;
                gpt_api = document.getElementById("gptApiKeyInput").value;
                if (!gpt_api || !llm_model) {
                    showToast('Select a GPT LLM and indicate your API Key.');
                    return;
                }
            } else {
                showToast('Select GPT, Gemini, or Ollama.');
                return;
            }

            labelTopic = {
                "llm_type": llm_type,
                "llm": llm_model,
                "gpt_api": gpt_api,
                "ollama_server": ollama_server,
            };
        }

        const data = {
            "dataset": dataset,
            "output": outputPath,
            "lang1": lang1.toUpperCase(),
            "lang2": (lang2 && lang2 !== "mono") ? lang2.toUpperCase() : "",
            "k": kTopics,
            "labelTopic": labelTopic,
        };

        console.log(data);

        // Disable button and show spinner
        btn.disabled = true;
        const originalHTML = btn.innerHTML;
        btn.innerHTML = `
            <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
            Starting Topic Modeling...
        `;

        fetch("/preprocess/Stage2", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(err => {
                        throw new Error(err.message || `HTTP Error: ${response.status}`);
                    });
                }
                return response.json();
            })
            .then(response => {
                console.log('Success (' + response.status + '): ' + response.message);
                updateProgressBar();
                // Re-enable button
                btn.disabled = false;
                btn.innerHTML = originalHTML;
            })
            .catch(error => {
                console.error("Error in Fetch/AJAX:", error.message);
                showToast(`Couldn\'t start new TopicModel process because ${error.message}`);
                // Re-enable button on error
                btn.disabled = false;
                btn.innerHTML = originalHTML;
            });
    });
}

/* ──────────────────────────────────────────────────────────
   Stage 3: Download
   ────────────────────────────────────────────────────────── */
function initStage3() {
    const stageDownload = document.getElementById("stage-download");
    const confirmDownload = document.getElementById("confirmDownload");
    if (!stageDownload || !confirmDownload) return;

    stageDownload.addEventListener("change", function () {
        if (this.value == 3) confirmDownload.textContent = 'Download Topic Model';
        else confirmDownload.textContent = 'Download Dataset';
    });

    confirmDownload.addEventListener("click", function () {
        const stage = stageDownload.value;

        if (!stage) {
            showToast("Please fill the Stage option.");
            return;
        }

        const dataset = document.getElementById("optionsDatasets3-" + stage).value;
        const outputPath = document.getElementById("outputPath3").value.trim();
        const formatFile = document.getElementById("formatFile3").value;

        if (stage == 3) {
            if (!dataset || !outputPath) {
                showToast("Please fill in all fields before continuing.");
                return;
            }
        } else {
            if (!dataset || !outputPath || !formatFile) {
                showToast("Please fill in all fields before continuing.");
                return;
            }
        }

        let output = "";
        if (stage === "1" || stage === "2") {
            output = outputPath + "." + formatFile;
        } else if (stage === "3") {
            output = outputPath + ".zip";
        }

        const data = {
            "stage": stage,
            "dataset": dataset,
            "output": output,
            "format": formatFile
        };

        console.log(data);

        this.style.pointerEvents = 'none';
        this.style.opacity = '0.6';
        this.classList.add('disabled');

        const originalHTML = this.innerHTML;
        this.innerHTML = `
        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
        Waiting...
    `;

        fetch("/preprocess/download", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(err => { throw new Error(err.message || `HTTP Error: ${response.status}`); });
                }
                return response.blob();
            })
            .then(blob => {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = data.output;
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);
                console.log("Download started.");
                this.style.pointerEvents = 'auto';
                this.style.opacity = '1';
                this.classList.remove('disabled');
                this.innerHTML = originalHTML;
                updateProgressBar();
            })
            .catch(error => {
                this.style.pointerEvents = 'auto';
                this.style.opacity = '1';
                this.classList.remove('disabled');
                this.innerHTML = originalHTML;
                console.error("Error in Fetch/AJAX:", error.message);
            });
    });
}

/* ──────────────────────────────────────────────────────────
   Download Stage Selector Visibility
   ────────────────────────────────────────────────────────── */
function initDownloadStageSelector() {
    const stageSelect = document.getElementById('stage-download');
    if (!stageSelect) return;

    const labelDataset = document.getElementById('optionsDatasets3');
    const labelFormat = document.getElementById('optionsFormatFile3');
    const formatFile = document.getElementById('formatFile3');
    const options1 = document.getElementById('optionsDatasets3-1');
    const options2 = document.getElementById('optionsDatasets3-2');
    const options3 = document.getElementById('optionsDatasets3-3');

    stageSelect.addEventListener('change', function () {
        const selectedValue = this.value;

        if (selectedValue === '1') {
            labelDataset.style.display = '';
            labelFormat.style.display = '';
            formatFile.style.display = '';
            options1.style.display = '';
            options2.style.display = 'none';
            options3.style.display = 'none';
        } else if (selectedValue === '2') {
            labelDataset.style.display = '';
            labelFormat.style.display = '';
            formatFile.style.display = '';
            options1.style.display = 'none';
            options2.style.display = '';
            options3.style.display = 'none';
        } else if (selectedValue === '3') {
            labelDataset.style.display = '';
            labelFormat.style.display = 'none';
            formatFile.style.display = 'none';
            options1.style.display = 'none';
            options2.style.display = 'none';
            options3.style.display = '';
        } else {
            labelDataset.style.display = 'none';
            labelFormat.style.display = 'none';
            formatFile.style.display = 'none';
            options1.style.display = 'none';
            options2.style.display = 'none';
            options3.style.display = 'none';
        }
    });
}

/* ──────────────────────────────────────────────────────────
   Step-Slide Carousel (Step 1 sub-slides)
   ────────────────────────────────────────────────────────── */
let currentSlide = 0;

function initSlideCarousel() {
    const slides = document.querySelectorAll('#modal-body-1 .step-slide');
    const modalBody1 = document.getElementById('modal-body-1');
    if (!slides.length || !modalBody1) return;

    const totalSlides = slides.length;
    const nextBtn = document.getElementById('nextSlide');
    const prevBtn = document.getElementById('prevSlide');
    const preprocessBtn = document.getElementById('confirmDatasetPreprocess');

    function adjustHeight(index) {
        const slide = slides[index];
        if (slide) {
            const slideHeight = slide.scrollHeight;
            modalBody1.style.height = slideHeight + 'px';
        }
    }

    function showSlide(index) {
        slides.forEach((slide, i) => {
            slide.classList.remove('active-slide', 'previous-slide');
            if (i < index) slide.classList.add('previous-slide');
            else if (i === index) slide.classList.add('active-slide');
        });

        activeResizeObserver.disconnect();
        const activeSlide = slides[index];
        activeResizeObserver.observe(activeSlide);

        currentSlide = index;
        updateNav();
        adjustHeight(currentSlide);
    }

    function updateNav() {
        prevBtn.style.display = currentSlide > 0 ? '' : 'none';
        nextBtn.style.display = currentSlide < totalSlides - 1 ? '' : 'none';
        preprocessBtn.style.display = currentSlide === totalSlides - 1 ? '' : 'none';
    }

    function validateInputsTranslator() {
        const textCol = document.getElementById('TextColumn-Segmentor').value.trim();
        const langCol = document.getElementById('LanguageColumnTranslator').value.trim();
        const sourceLang = document.getElementById('SourceLanguage').value;
        const targetLang = document.getElementById('TargetLanguage').value;

        const validCombinations = [
            ["en", "es"], ["es", "en"],
            ["en", "de"], ["de", "en"],
            ["en", "it"], ["it", "en"]
        ];

        const isMono = targetLang === 'mono';

        if (!textCol) {
            showToast("Text Column cannot be empty.");
            return false;
        }

        // If not monolingual, we need the language column to split the data
        if (!isMono && !langCol) {
            showToast("Language Column cannot be empty for bilingual datasets.");
            return false;
        }

        if (isMono) {
            if (!sourceLang) {
                showToast("Please select the Source Language.");
                return false;
            }
            return true;
        }

        const isValidCombo = validCombinations.some(
            combo => combo[0] === sourceLang && combo[1] === targetLang
        );

        if (!isValidCombo) {
            showToast("Invalid Source and Target language combination.");
            return false;
        }
        return true;
    }

    function verifyParamsSlide(idx) {
        if (idx == 0) {
            const selector = document.getElementById("optionsDatasets1");
            const dbSelected = selector.value;
            const OutputPathInput = document.getElementById("TextColumnOutput-Segmentor").value.trim();

            if (dbSelected == "" || OutputPathInput == "") {
                showToast("Select dataset to preprocess and an output name.");
                return false;
            }
            return true;
        } else if (idx == 1) {
            const textColumnInput = document.getElementById("TextColumn-Segmentor").value;
            const idColumnInput = document.getElementById("IdColumn-Segmentor").value;
            const minLengthInput = document.getElementById("MinimumLength-Segmentor").value;
            const separatorInput = document.getElementById("Separator-Segmentor").value;

            if (textColumnInput == "") {
                showToast("Indicate the text label to preprocess.");
                return false;
            }
            if (idColumnInput == "") {
                showToast("Indicate the id label to preprocess.");
                return false;
            }

            if (!(/^-?\d+$/.test(minLengthInput))) {
                showToast("Minimum Length must be an integer.");
                return false;
            } else if (minLengthInput <= 0) {
                showToast("Minimum Length should be equal or greater than 1, so it will be used 100 as Minimum Length.", 'warning');
            }

            if (separatorInput == "") {
                showToast("The separator input is empty, so it will be used \\n as separator.", 'warning');
            }

            return true;
        } else if (idx == 2) {
            return validateInputsTranslator();
        }
        return false;
    }

    nextBtn.addEventListener('click', () => {
        let verified = verifyParamsSlide(currentSlide);
        if (verified && currentSlide < totalSlides - 1) showSlide(currentSlide + 1);
    });

    prevBtn.addEventListener('click', () => {
        if (currentSlide > 0) showSlide(currentSlide - 1);
    });

    const stepModalEl = document.getElementById('stepModal');
    stepModalEl.addEventListener('hidden.bs.modal', function () {
        showSlide(0);
    });

    const activeResizeObserver = new ResizeObserver(() => {
        adjustHeight(currentSlide);
    });

    showSlide(0);
    window.addEventListener('resize', () => adjustHeight(currentSlide));

    // Details text content
    const detailsSlide2 = document.getElementById('detailsSlide2-text');
    if (detailsSlide2) {
        detailsSlide2.textContent = 'The Segmenter Component allows to split documents into segments. Options:\n\n' +
            ' - Text Column\t\t\tName of the text column to segment.\n' +
            ' - Id Column\t\t\tName of the id column to identify.\n' +
            ' - Minimum Length\tMinimum length for a paragraph to be kept.\n' +
            ' - Separator\t\t\t\tSeparator for splitting paragraphs.';
    }

    const detailsSlide3 = document.getElementById('detailsSlide3-text');
    if (detailsSlide3) {
        detailsSlide3.textContent = 'The Translator Component allows to translate a dataset from one language to another. For monolingual datasets, select "N/A (Monolingual)" as the Target Language to skip this step.\n\n' +
            ' - Source Language\tSource language of the dataset.\n' +
            ' - Target Language\tTarget language to translate to.\n' +
            ' - Language Column\tColumn name that contains the language of each document.';
    }

    const details2TopicModeling = document.getElementById('details2-TopicModeling-text');
    if (details2TopicModeling) {
        details2TopicModeling.textContent = 'The Topic Modeling Component trains a topic model. For bilingual datasets it uses the Polylingual model; for monolingual datasets it uses standard LDA. Options:\n\n' +
            ' - Lang 1\t\t\t\tFirst language code.\n' +
            ' - Lang 2\t\t\t\tSecond language code (or N/A for monolingual).\n' +
            ' - K Topics\t\t\tNumber of topics to extract.\n' +
            ' - Label Topic\t\tCreates a label for each topic to classify the documents.';
    }

    // Collapsible details toggles
    const toggles = document.querySelectorAll('.details-toggle');
    toggles.forEach(toggle => {
        const targetId = toggle.getAttribute('data-target');
        const collapseEl = document.querySelector(targetId);
        if (!collapseEl) return;

        collapseEl.addEventListener('shown.bs.collapse', () => { toggle.classList.add('active'); });
        collapseEl.addEventListener('hidden.bs.collapse', () => { toggle.classList.remove('active'); });

        toggle.addEventListener('click', () => {
            const bsCollapse = bootstrap.Collapse.getOrCreateInstance(collapseEl, { toggle: false });
            const isShown = collapseEl.classList.contains('show');

            if (isShown) bsCollapse.hide();
            else bsCollapse.show();

            toggle.classList.toggle('active', !isShown);

            const start = performance.now();
            const duration = 350;
            const monitor = setInterval(() => {
                showSlide(currentSlide);
                if (performance.now() - start > duration) clearInterval(monitor);
            }, 16);
        });
    });
}

/* ──────────────────────────────────────────────────────────
   Main Initialization
   ────────────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", function () {
    initModelSelector();
    initLabelTopicToggle();
    initLLMTypeVisibility();
    initStepModal();
    initStage2();
    initStage3();
    initDownloadStageSelector();
    initSlideCarousel();
});
