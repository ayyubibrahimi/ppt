'use client'

import { useState } from 'react'
import { createClientComponentClient } from '@supabase/auth-helpers-nextjs'
import { AlertTriangle, Eye, EyeOff, Mail, User, Phone, Building } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import styles from './AuthPage.module.scss'

interface AuthPageProps {
  onAuthSuccess: (user: {
    id: string
    email?: string
    user_metadata?: {
      full_name?: string
      phone?: string
      organization?: string
    }
  }) => void
}

interface SignUpFormData {
  email: string
  password: string
  fullName: string
  phone: string
  organization: string
}

export default function AuthPage({ onAuthSuccess }: AuthPageProps) {
  const supabase = createClientComponentClient()
  
  // State
  const [isSignUp, setIsSignUp] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showPassword, setShowPassword] = useState(false)
  
  // Form data
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [signUpData, setSignUpData] = useState<SignUpFormData>({
    email: '',
    password: '',
    fullName: '',
    phone: '',
    organization: ''
  })

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!email || !password) {
      setError('Please enter both email and password')
      return
    }
    
    try {
      setIsLoading(true)
      setError(null)
      
      console.log('=== SIGN IN DEBUG ===')
      console.log('Attempting sign:', email)
      
      const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password
      })
      
      console.log('Sign in response data:', data)
      console.log('Sign in error:', error)
      
      if (error) throw error
      
      if (data.user) {
        console.log('Sign in successful, calling onAuthSuccess...')
        
        onAuthSuccess(data.user)
      }
      
    } catch (err: unknown) {
      console.error('Sign in error:', err)
      const errorMessage = err instanceof Error ? err.message : 'Failed to sign in. Please try again.'
      setError(errorMessage)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!signUpData.email || !signUpData.password || !signUpData.fullName) {
      setError('Please fill in all required fields')
      return
    }
    
    if (signUpData.password.length < 6) {
      setError('Password must be at least 6 characters')
      return
    }
    
    try {
      setIsLoading(true)
      setError(null)
      
      // Sign up with Supabase Auth
      const { data, error } = await supabase.auth.signUp({
        email: signUpData.email,
        password: signUpData.password
      })
      
      if (error) throw error
      
      if (data.user) {
        // Create user profile in users table
        const { error: profileError } = await supabase
          .from('users')
          .insert({
            id: data.user.id,
            email: signUpData.email,
            full_name: signUpData.fullName,
            phone: signUpData.phone || null,
            organization: signUpData.organization || null,
            is_active: true,
            last_login: new Date().toISOString()
          })
        
        if (profileError) {
          console.error('Profile creation error:', profileError)
          // Continue anyway - auth was successful
        }
        
        onAuthSuccess(data.user)
      }
      
    } catch (err: unknown) {
      console.error('Sign in error:', err)
      const errorMessage = err instanceof Error ? err.message : 'Failed to sign in. Please try again.'
      setError(errorMessage)
    } finally {
      setIsLoading(false)
    }
  }



  const toggleMode = () => {
    setIsSignUp(!isSignUp)
    setError(null)
    setEmail('')
    setPassword('')
    setSignUpData({
      email: '',
      password: '',
      fullName: '',
      phone: '',
      organization: ''
    })
  }

  return (
    <div className={styles.container}>
      {/* Left Side - Branding */}
      <div className={styles.brandingSide}>
        <div className={styles.brandingContent}>
          <div className={styles.logo}>
            <span className={styles.brandingTitle}>Public Paper Trail</span>
          </div>
          
          <div className={styles.brandingText}>
            <h1 className={styles.brandingTitle}>
              Automate Your Public Records Requests
            </h1>
            <p className={styles.brandingSubtitle}>
              Submit, track, and manage public records requests with an agent in one unified platform.
            </p>
          </div>
        
        </div>
      </div>

      {/* Right Side - Auth Form */}
      <div className={styles.authSide}>
        <div className={styles.authContainer}>
          <div className={styles.authHeader}>
            <div className={styles.authToggle}>
              <button
                type="button"
                onClick={toggleMode}
                className={styles.toggleLink}
              >
                {isSignUp ? 'Login' : 'Sign Up'}
              </button>
            </div>
          </div>

          <div className={styles.authForm}>
            <div className={styles.formHeader}>
              <h2 className={styles.formTitle}>
                {isSignUp ? 'Create an account' : 'Welcome back'}
              </h2>
              <p className={styles.formSubtitle}>
                {isSignUp 
                  ? 'Enter your details below to create your account'
                  : 'Enter your credentials to access your account'
                }
              </p>
            </div>

            {/* Error Banner */}
            {error && (
              <div className={styles.errorBanner}>
                <AlertTriangle className={styles.errorIcon} />
                <span className={styles.errorText}>{error}</span>
              </div>
            )}

            {/* Sign Up Form */}
            {isSignUp ? (
              <form onSubmit={handleSignUp} className={styles.form}>
                <div className={styles.formField}>
                  <div className={styles.inputWrapper}>
                    <Mail className={styles.inputIcon} />
                    <Input
                      type="email"
                      placeholder="name@example.com"
                      value={signUpData.email}
                      onChange={(e) => setSignUpData(prev => ({ ...prev, email: e.target.value }))}
                      className={styles.input}
                      required
                    />
                  </div>
                </div>

                <div className={styles.formField}>
                  <div className={styles.inputWrapper}>
                    <User className={styles.inputIcon} />
                    <Input
                      type="text"
                      placeholder="Full Name"
                      value={signUpData.fullName}
                      onChange={(e) => setSignUpData(prev => ({ ...prev, fullName: e.target.value }))}
                      className={styles.input}
                      required
                    />
                  </div>
                </div>

                <div className={styles.formRow}>
                  <div className={styles.formField}>
                    <div className={styles.inputWrapper}>
                      <Phone className={styles.inputIcon} />
                      <Input
                        type="tel"
                        placeholder="Phone (optional)"
                        value={signUpData.phone}
                        onChange={(e) => setSignUpData(prev => ({ ...prev, phone: e.target.value }))}
                        className={styles.input}
                      />
                    </div>
                  </div>
                  
                  <div className={styles.formField}>
                    <div className={styles.inputWrapper}>
                      <Building className={styles.inputIcon} />
                      <Input
                        type="text"
                        placeholder="Organization (optional)"
                        value={signUpData.organization}
                        onChange={(e) => setSignUpData(prev => ({ ...prev, organization: e.target.value }))}
                        className={styles.input}
                      />
                    </div>
                  </div>
                </div>

                <div className={styles.formField}>
                  <div className={styles.inputWrapper}>
                    <div className={styles.passwordField}>
                      <Input
                        type={showPassword ? "text" : "password"}
                        placeholder="Password (min 6 characters)"
                        value={signUpData.password}
                        onChange={(e) => setSignUpData(prev => ({ ...prev, password: e.target.value }))}
                        className={styles.passwordInput}
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className={styles.passwordToggle}
                      >
                        {showPassword ? <EyeOff className={styles.eyeIcon} /> : <Eye className={styles.eyeIcon} />}
                      </button>
                    </div>
                  </div>
                </div>

                <Button
                  type="submit"
                  disabled={isLoading}
                  className={styles.submitButton}
                >
                  {isLoading ? 'Creating account...' : 'Create Account'}
                </Button>
              </form>
            ) : (
              /* Sign In Form */
              <form onSubmit={handleSignIn} className={styles.form}>
                <div className={styles.formField}>
                  <div className={styles.inputWrapper}>
                    <Mail className={styles.inputIcon} />
                    <Input
                      type="email"
                      placeholder="name@example.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className={styles.input}
                      required
                    />
                  </div>
                </div>

                <div className={styles.formField}>
                  <div className={styles.inputWrapper}>
                    <div className={styles.passwordField}>
                      <Input
                        type={showPassword ? "text" : "password"}
                        placeholder="Password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        className={styles.passwordInput}
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className={styles.passwordToggle}
                      >
                        {showPassword ? <EyeOff className={styles.eyeIcon} /> : <Eye className={styles.eyeIcon} />}
                      </button>
                    </div>
                  </div>
                </div>

                <Button
                  type="submit"
                  disabled={isLoading}
                  className={styles.submitButton}
                >
                  {isLoading ? 'Signing in...' : 'Sign In'}
                </Button>
              </form>
            )}

          </div>
        </div>
      </div>
    </div>
  )
}