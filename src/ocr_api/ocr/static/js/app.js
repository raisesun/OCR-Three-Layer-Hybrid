/**
 * OCR演示 - Alpine.js主应用
 */

function app() {
    return {
        // Tab状态
        activeTab: 'single',
        tabs: [
            { id: 'single', label: '📷 单图处理' },
            { id: 'async', label: '📤 异步任务' },
            { id: 'compare', label: '📊 基线对比' },
            { id: 'stats', label: '📈 统计面板' },
        ],

        // 单图处理
        dragOver: false,
        uploadedImageUrl: null,
        uploadedImagePath: null,
        currentImagePath: '',
        ocrText: '',
        processing: false,
        processResult: null,
        selectedCase: '',
        selectedImagePath: '',
        cases: [],
        caseImages: [],

        // 批量处理
        batchCaseId: '',
        batchProcessing: false,
        batchResults: [],
        batchTotal: 0,
        batchStats: {},
        batchMode: 'case',  // 'case' 或 'directory'

        // 目录选择
        batchDirPath: '',
        batchDirCurrent: '',
        batchDirBreadcrumb: [],
        batchSubdirs: [],

        // 基线对比
        compareRunning: false,
        compareResult: null,

        // 统计面板
        dashboardData: null,
        dashboardLoading: false,

        // 异步任务管理
        asyncTasks: [],
        asyncTasksTotal: 0,
        asyncTasksPage: 1,
        asyncTasksPages: 0,
        asyncTasksLoading: false,
        asyncTaskFilter: '',  // 状态过滤
        asyncTaskSubmitting: false,
        asyncTaskSelectedFiles: [],
        asyncTaskPollTimer: null,
        asyncTaskDetail: null,  // 当前查看详情的任务
        asyncTaskDetailLoading: false,

        // 初始化
        async init() {
            await this.loadCases();
        },

        // ========== 数据加载 ==========

        async loadCases() {
            try {
                const res = await fetch('/api/baseline/cases');
                const data = await res.json();
                if (data.success) {
                    this.cases = data.data.cases;
                }
            } catch (e) {
                console.error('加载业务列表失败:', e);
            }
        },

        async loadCaseImages() {
            if (!this.selectedCase) {
                this.caseImages = [];
                return;
            }
            try {
                const res = await fetch(`/api/baseline/cases/${this.selectedCase}`);
                const data = await res.json();
                if (data.success) {
                    this.caseImages = data.data.images;
                }
            } catch (e) {
                console.error('加载图片列表失败:', e);
            }
        },

        async loadSelectedImage() {
            if (!this.selectedImagePath) return;
            const img = this.caseImages.find(i => i.file_path === this.selectedImagePath);
            if (img) {
                this.currentImagePath = img.file_path;
                this.ocrText = img.text || '';
                this.uploadedImageUrl = this.getImageUrl(img.file_path);
                this.processResult = null;
            }
        },

        // ========== 单图处理 ==========

        handleFileSelect(event) {
            const file = event.target.files[0];
            if (file) this.uploadFile(file);
        },

        handleDrop(event) {
            this.dragOver = false;
            const file = event.dataTransfer.files[0];
            if (file && file.type.startsWith('image/')) this.uploadFile(file);
        },

        async uploadFile(file) {
            const formData = new FormData();
            formData.append('file', file);
            try {
                const res = await fetch('/api/upload', { method: 'POST', body: formData });
                const data = await res.json();
                if (data.success) {
                    this.uploadedImageUrl = data.data.url;
                    this.uploadedImagePath = data.data.file_path;
                    this.currentImagePath = data.data.file_path;
                    this.ocrText = '';
                    this.processResult = null;
                }
            } catch (e) {
                console.error('上传失败:', e);
            }
        },

        async processImage() {
            this.processing = true;
            this.processResult = null;
            const imagePath = this.uploadedImagePath || this.currentImagePath;
            try {
                const res = await fetch('/api/process', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ image_path: imagePath, ocr_text: this.ocrText }),
                });
                const data = await res.json();
                if (data.success) {
                    this.processResult = data.data;
                } else {
                    alert('处理失败: ' + (data.error || '未知错误'));
                }
            } catch (e) {
                console.error('处理失败:', e);
                alert('处理失败: ' + e.message);
            } finally {
                this.processing = false;
            }
        },

        // ========== Pipeline流程图辅助 ==========

        isStagePassed(stageId) {
            if (!this.processResult?.pipeline_flow) return false;
            const active = this.processResult.pipeline_flow.active_stage;
            const stageOrder = ['stage0', 'stage1', 'stage1_5', 'stage1_6', 'stage2', 'stage3', 'stage4'];
            const activeIdx = stageOrder.indexOf(active);
            const currentIdx = stageOrder.indexOf(stageId);
            return currentIdx < activeIdx;
        },

        // ========== 批量处理 ==========

        async runBatch() {
            if (!this.batchCaseId) return;
            this.batchProcessing = true;
            this.batchResults = [];
            this.batchStats = {};

            try {
                // 先获取图片总数
                const caseRes = await fetch(`/api/baseline/cases/${this.batchCaseId}`);
                const caseData = await caseRes.json();
                if (caseData.success) {
                    this.batchTotal = caseData.data.images.length;
                }

                // 运行批量处理
                const res = await fetch('/api/process/batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ case_id: this.batchCaseId }),
                });
                const data = await res.json();
                if (data.success) {
                    this.batchResults = data.data.results;
                    this.batchStats = data.data.stats;
                    this.batchTotal = data.data.stats.total;
                }
            } catch (e) {
                console.error('批量处理失败:', e);
            } finally {
                this.batchProcessing = false;
            }
        },

        // ========== 目录批量处理 ==========

        async loadDirectories(parentPath) {
            try {
                const url = parentPath
                    ? `/api/directories?parent=${encodeURIComponent(parentPath)}`
                    : '/api/directories';
                const res = await fetch(url);
                const data = await res.json();
                if (data.success) {
                    this.batchDirCurrent = data.data.current_path;
                    this.batchSubdirs = data.data.directories;
                    this.batchDirPath = data.data.current_path;
                    this.buildBreadcrumb(data.data.current_path);
                }
            } catch (e) {
                console.error('加载目录失败:', e);
            }
        },

        buildBreadcrumb(currentPath) {
            const base = '/Users/dongsun/Github/sample-OCR';
            const relative = currentPath.replace(base, '').replace(/^\//, '');
            const parts = relative ? relative.split('/') : [];
            this.batchDirBreadcrumb = [
                { name: 'sample-OCR', path: base },
                ...parts.map((p, i) => ({
                    name: p,
                    path: base + '/' + parts.slice(0, i + 1).join('/'),
                })),
            ];
        },

        clickDirectory(dir) {
            if (dir.has_subdirs) {
                // 有子目录：进入子目录
                this.loadDirectories(dir.path);
            } else {
                // 叶子目录：选中用于处理
                this.batchDirPath = dir.path;
            }
        },

        async runBatchFromDirectory() {
            if (!this.batchDirPath) return;
            this.batchProcessing = true;
            this.batchResults = [];
            this.batchStats = {};

            try {
                const res = await fetch('/api/process/batch/directory', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ dir_path: this.batchDirPath }),
                });
                const data = await res.json();
                if (data.success) {
                    this.batchResults = data.data.results;
                    this.batchStats = data.data.stats;
                    this.batchTotal = data.data.stats.total;
                } else {
                    alert('处理失败: ' + (data.error || '未知错误'));
                }
            } catch (e) {
                console.error('目录批量处理失败:', e);
            } finally {
                this.batchProcessing = false;
            }
        },

        // ========== 基线对比 ==========

        async runCompare() {
            this.compareRunning = true;
            this.compareResult = null;
            try {
                const res = await fetch('/api/baseline/compare', { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    this.compareResult = data.data;
                    // 延迟渲染图表
                    setTimeout(() => renderCompareCharts(), 100);
                }
            } catch (e) {
                console.error('基线对比失败:', e);
            } finally {
                this.compareRunning = false;
            }
        },

        // ========== 统计面板 ==========

        async loadDashboard() {
            try {
                this.dashboardLoading = true;
                const res = await fetch('/api/stats/dashboard');
                const data = await res.json();
                if (data.success) {
                    // 使用 Alpine.js $nextTick 确保响应性更新
                    this.dashboardData = data.data;
                    await this.$nextTick();
                    setTimeout(() => renderDashboardCharts(), 200);
                }
            } catch (e) {
                console.error('加载统计失败:', e);
            } finally {
                this.dashboardLoading = false;
            }
        },

        // ========== 工具方法 ==========

        // ========== 异步任务管理 ==========

        async loadAsyncTasks(page = 1) {
            this.asyncTasksLoading = true;
            try {
                const params = new URLSearchParams({ page: page, size: 10 });
                if (this.asyncTaskFilter) params.append('status', this.asyncTaskFilter);
                const res = await fetch(`/api/debug/tasks?${params}`);
                const json = await res.json();
                if (json.code === 200) {
                    this.asyncTasks = json.data.tasks;
                    this.asyncTasksTotal = json.data.total;
                    this.asyncTasksPage = json.data.page;
                    this.asyncTasksPages = json.data.pages;
                }
            } catch (e) {
                console.error('加载任务列表失败:', e);
            } finally {
                this.asyncTasksLoading = false;
            }
        },

        handleAsyncFileSelect(event) {
            this.asyncTaskSelectedFiles = Array.from(event.target.files);
        },

        async submitAsyncTask() {
            if (this.asyncTaskSelectedFiles.length === 0) return;
            this.asyncTaskSubmitting = true;
            try {
                const formData = new FormData();
                this.asyncTaskSelectedFiles.forEach(f => formData.append('files', f));
                const res = await fetch('/api/debug/ocr/async', {
                    method: 'POST',
                    body: formData,
                });
                const json = await res.json();
                if (json.code === 202) {
                    alert(`任务已提交！task_id: ${json.data.task_id}`);
                    this.asyncTaskSelectedFiles = [];
                    // 重置文件输入
                    const fileInput = document.getElementById('asyncFileInput');
                    if (fileInput) fileInput.value = '';
                    // 刷新任务列表
                    await this.loadAsyncTasks();
                    // 启动轮询
                    this.startTaskPolling();
                } else {
                    alert('提交失败: ' + (json.message || '未知错误'));
                }
            } catch (e) {
                console.error('提交失败:', e);
                alert('提交失败: ' + e.message);
            } finally {
                this.asyncTaskSubmitting = false;
            }
        },

        async viewTaskDetail(taskId) {
            this.asyncTaskDetailLoading = true;
            try {
                const res = await fetch(`/api/debug/task/${taskId}`);
                const json = await res.json();
                if (json.code === 200) {
                    this.asyncTaskDetail = json.data;
                }
            } catch (e) {
                console.error('加载任务详情失败:', e);
            } finally {
                this.asyncTaskDetailLoading = false;
            }
        },

        async cancelTask(taskId) {
            if (!confirm('确定要取消此任务吗？')) return;
            try {
                const res = await fetch(`/api/debug/task/${taskId}/cancel`, { method: 'POST' });
                const json = await res.json();
                if (json.code === 200) {
                    await this.loadAsyncTasks(this.asyncTasksPage);
                } else {
                    alert('取消失败: ' + (json.message || json.detail || '未知错误'));
                }
            } catch (e) {
                console.error('取消失败:', e);
            }
        },

        startTaskPolling() {
            if (this.asyncTaskPollTimer) return;
            this.asyncTaskPollTimer = setInterval(async () => {
                // 检查是否有进行中的任务
                const hasActive = this.asyncTasks.some(
                    t => t.status === 'pending' || t.status === 'processing'
                );
                if (hasActive) {
                    await this.loadAsyncTasks(this.asyncTasksPage);
                } else {
                    this.stopTaskPolling();
                }
            }, 3000);
        },

        stopTaskPolling() {
            if (this.asyncTaskPollTimer) {
                clearInterval(this.asyncTaskPollTimer);
                this.asyncTaskPollTimer = null;
            }
        },

        getStatusColor(status) {
            const colors = {
                pending: 'bg-yellow-100 text-yellow-700',
                processing: 'bg-blue-100 text-blue-700',
                completed: 'bg-green-100 text-green-700',
                failed: 'bg-red-100 text-red-700',
                cancelled: 'bg-gray-100 text-gray-500',
            };
            return colors[status] || 'bg-gray-100 text-gray-700';
        },

        getStatusLabel(status) {
            const labels = {
                pending: '等待中',
                processing: '处理中',
                completed: '已完成',
                failed: '失败',
                cancelled: '已取消',
            };
            return labels[status] || status;
        },

        formatTime(isoStr) {
            if (!isoStr) return '-';
            const d = new Date(isoStr);
            return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
        },

        getImageUrl(filePath) {
            if (!filePath) return '';
            // 基线图片路径: /Users/dongsun/Github/sample-OCR/...
            const idx = filePath.indexOf('sample-OCR/');
            if (idx >= 0) {
                return '/sample-images/' + filePath.substring(idx + 'sample-OCR/'.length);
            }
            // 上传的图片
            if (filePath.includes('upload_')) {
                return '/uploads/' + filePath.split('/').pop();
            }
            return filePath;
        },
    };
}
