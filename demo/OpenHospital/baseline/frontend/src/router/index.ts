import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'Dashboard',
      component: () => import('@/views/Dashboard.vue'),
      meta: { title: 'OpenHospital' },
    },
    {
      path: '/doctor/:id',
      name: 'DoctorDetail',
      component: () => import('@/views/DoctorView.vue'),
      meta: { title: 'DoctorDetails' },
    },
    {
      path: '/patient/:id',
      name: 'PatientDetail',
      component: () => import('@/views/PatientView.vue'),
      meta: { title: 'PatientDetails' },
    },
  ],
})
router.beforeEach((to, _from, next) => {
  document.title = (to.meta.title as string) || 'OpenHospital'
  next()
})

export default router

